import ast

class PyToCTranslator(ast.NodeVisitor):
    def __init__(self):
        self.c_code = []
        self.indent = 0
        self.var_types = {}
        self.var_dims = {}
        self.need_malloc = False
        self.current_func = None
        self.has_main = False          # флаг, что мы создали main сами

    def indent_inc(self): self.indent += 1
    def indent_dec(self): self.indent -= 1
    def emit(self, line): self.c_code.append('    ' * self.indent + line)

    def translate(self, tree):
        self.visit(tree)
        return '\n'.join(self.c_code)

    # Сбор переменных
    class VarCollector(ast.NodeVisitor):
        def __init__(self):
            self.vars = set()
        def visit_Name(self, node):
            if isinstance(node.ctx, (ast.Store, ast.Load)):
                self.vars.add(node.id)
        def visit_FunctionDef(self, node):
            pass  # не заходим в подфункции

    # Обход модуля
    def visit_Module(self, node):
        # Проверяем, есть ли в теле функции
        has_func = any(isinstance(stmt, ast.FunctionDef) for stmt in node.body)
        if not has_func:
            # Нет функции – создаём main
            self.has_main = True
            # Создаём синтетическое тело main из всех statements
            main_body = node.body
            # Сначала соберём все переменные, чтобы объявить их в начале main
            collector = self.VarCollector()
            for stmt in main_body:
                collector.visit(stmt)
            # Заголовок main
            self.emit("int main() {")
            self.indent_inc()
            # Объявление переменных
            for var in sorted(collector.vars):
                if var not in self.var_types:
                    self.var_types[var] = 'double'
                self.emit(f"{self.var_types[var]} {var};")
            # Генерируем тело
            for stmt in main_body:
                self.visit(stmt)
            self.indent_dec()
            self.emit("}")
        else:
            for stmt in node.body:
                self.visit(stmt)

    # Функции
    def visit_FunctionDef(self, node):
        self.current_func = node.name
        collector = self.VarCollector()
        for stmt in node.body:
            collector.visit(stmt)
        args = [arg.arg for arg in node.args.args]
        for a in args:
            collector.vars.add(a)

        if len(args) == 1:
            self.emit(f"int {self.current_func}(int *{args[0]}, int len) {{")
            self.var_types[args[0]] = "int*"
        elif len(args) == 2:
            self.emit(f"int {self.current_func}(int *{args[0]}, int {args[1]}) {{")
            self.var_types[args[0]] = "int*"
        else:
            raise NotImplementedError("1 или 2 аргумента")
        self.indent_inc()

        for var in sorted(collector.vars):
            if var in args:
                continue
            if var not in self.var_types:
                self.var_types[var] = 'double'
            self.emit(f"{self.var_types[var]} {var};")

        for stmt in node.body:
            self.visit(stmt)

        self.indent_dec()
        self.emit("}")
        self.current_func = None

    # Присваивание (с распознаванием int(input()) )
    def visit_Assign(self, node):
        if len(node.targets) != 1:
            raise NotImplementedError("Множественное присваивание")
        target = node.targets[0]

        # Присваивание элементу массива
        if isinstance(target, ast.Subscript):
            self._assign_subscript(target, node.value)
            return

        # Распознаём int(input()) или int(input("..."))
        if (isinstance(node.value, ast.Call) and
            isinstance(node.value.func, ast.Name) and node.value.func.id == 'int' and
            len(node.value.args) == 1 and
            isinstance(node.value.args[0], ast.Call) and
            isinstance(node.value.args[0].func, ast.Name) and node.value.args[0].func.id == 'input'):
            # int(input(...))
            input_call = node.value.args[0]
            self._gen_int_input_assign(target, input_call)
            return

        # Обычный input() (строковый)
        if (isinstance(node.value, ast.Call) and
            isinstance(node.value.func, ast.Name) and
            node.value.func.id == 'input'):
            self._gen_input_assign(target, node.value)
            return

        if not isinstance(target, ast.Name):
            raise NotImplementedError(f"Цель {type(target)}")
        var = target.id

        # Строковый литерал
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            s = node.value.value.replace('"', '\\"')
            self.var_types[var] = 'char*'
            self.need_malloc = True
            self.emit(f'{var} = strdup("{s}");')
            return

        # Конкатенация строк
        if (isinstance(node.value, ast.BinOp) and isinstance(node.value.op, ast.Add) and
            self._is_str(node.value.left) and self._is_str(node.value.right)):
            self.var_types[var] = 'char*'
            l_code = self._str_expr(node.value.left)
            r_code = self._str_expr(node.value.right)
            self.emit(f'{var} = malloc(strlen({l_code}) + strlen({r_code}) + 1);')
            self.emit(f'strcpy({var}, {l_code});')
            self.emit(f'strcat({var}, {r_code});')
            self.need_malloc = True
            return

        # Создание массива
        if isinstance(node.value, ast.List):
            self._assign_list(var, node.value)
            return

        # Динамический массив [0]*n
        if (isinstance(node.value, ast.BinOp) and isinstance(node.value.op, ast.Mult) and
            isinstance(node.value.left, ast.List) and len(node.value.left.elts) == 1 and
            isinstance(node.value.left.elts[0], ast.Constant) and node.value.left.elts[0].value == 0):
            _, size_code = self.gen_expr(node.value.right)
            self.emit(f"int *{var} = (int*)malloc({size_code} * sizeof(int));")
            self.var_types[var] = "int*"
            self.need_malloc = True
            return

        # Обычное выражение
        expr_type, expr_code = self.gen_expr(node.value)
        if var not in self.var_types:
            self.var_types[var] = expr_type
            self.emit(f"{expr_type} {var} = {expr_code};")
        else:
            if self.var_types[var] == 'int' and expr_type == 'double':
                self.var_types[var] = 'double'
            self.emit(f"{var} = {expr_code};")

    def _gen_int_input_assign(self, target, input_call):
        if not isinstance(target, ast.Name):
            raise NotImplementedError("int(input()) только в переменную")
        var = target.id
        # Определяем тип переменной как int
        self.var_types[var] = 'int'
        # Если есть подсказка в input
        if input_call.args:
            prompt = input_call.args[0]
            if isinstance(prompt, ast.Constant) and isinstance(prompt.value, str):
                self.emit(f'printf("{prompt.value}");')
        self.emit(f'scanf("%d", &{var});')

    def _is_str(self, node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return True
        if isinstance(node, ast.Name) and self.var_types.get(node.id, '').startswith('char*'):
            return True
        return False

    def _str_expr(self, node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return f'"{node.value.replace('"', '\\"')}"'
        if isinstance(node, ast.Name):
            return node.id
        raise NotImplementedError("Сложное строковое выражение")

    def _assign_subscript(self, subscript, value_node):
        if not isinstance(subscript.value, ast.Name):
            raise NotImplementedError("Индексация только по имени")
        arr_name = subscript.value.id
        _, idx_code = self.gen_expr(subscript.slice)
        _, val_code = self.gen_expr(value_node)
        self.emit(f"{arr_name}[{idx_code}] = {val_code};")

    def _assign_list(self, var, list_node):
        def is_2d(elts):
            return all(isinstance(e, ast.List) for e in elts)
        if is_2d(list_node.elts):
            rows = len(list_node.elts)
            cols = None
            flat = []
            for row in list_node.elts:
                if not isinstance(row, ast.List):
                    raise ValueError("Неоднородная размерность")
                if cols is None:
                    cols = len(row.elts)
                elif cols != len(row.elts):
                    raise ValueError("Не прямоугольная матрица")
                for elem in row.elts:
                    _, code = self.gen_expr(elem)
                    flat.append(code)
            if cols is None:
                cols = 0
            init = []
            idx = 0
            for r in range(rows):
                row_vals = flat[idx:idx+cols]
                init.append("{" + ", ".join(row_vals) + "}")
                idx += cols
            self.emit(f"int {var}[{rows}][{cols}] = {{{', '.join(init)}}};")
            self.var_types[var] = f"int[{rows}][{cols}]"
        else:
            elems = []
            elem_type = None
            for el in list_node.elts:
                t, code = self.gen_expr(el)
                if elem_type is None:
                    elem_type = t
                elif elem_type != t:
                    elem_type = 'double'
                elems.append(code)
            c_type = 'int' if elem_type == 'int' else 'double'
            self.emit(f"{c_type} {var}[] = {{{', '.join(elems)}}};")
            self.var_types[var] = f"{c_type}[]"

    def visit_AugAssign(self, node):
        target = node.target
        op = node.op
        if isinstance(target, ast.Name):
            var = target.id
            if var not in self.var_types:
                raise NameError(f"{var} не определена")
            if self.var_types[var] == 'char*':
                raise NotImplementedError("Строковые += не поддерживаются")
            expr_type, expr_code = self.gen_expr(node.value)
            if isinstance(op, ast.Div) and self.var_types[var] == 'int' and expr_type == 'int':
                self.emit(f"{var} = (double){var} / {expr_code};")
                self.var_types[var] = 'double'
            elif isinstance(op, ast.Pow):
                self.emit(f"{var} = pow({var}, {expr_code});")
                self.var_types[var] = 'double'
            else:
                op_map = {ast.Add:'+=', ast.Sub:'-=', ast.Mult:'*=', ast.Div:'/=',
                          ast.FloorDiv:'/=', ast.Mod:'%='}
                oper = op_map.get(type(op))
                if not oper:
                    raise NotImplementedError(f"Операция {type(op)}")
                self.emit(f"{var} {oper} {expr_code};")
        elif isinstance(target, ast.Subscript):
            arr_name = target.value.id
            _, idx_code = self.gen_expr(target.slice)
            _, expr_code = self.gen_expr(node.value)
            if isinstance(op, ast.Add):
                self.emit(f"{arr_name}[{idx_code}] += {expr_code};")
            elif isinstance(op, ast.Sub):
                self.emit(f"{arr_name}[{idx_code}] -= {expr_code};")
            else:
                raise NotImplementedError(f"AugAssign для индекса {type(op)}")
        else:
            raise NotImplementedError("AugAssign только для переменных")

    def visit_If(self, node):
        cond = self.gen_condition(node.test)
        self.emit(f"if ({cond}) {{")
        self.indent_inc()
        for stmt in node.body:
            self.visit(stmt)
        self.indent_dec()
        if node.orelse:
            if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
                self.emit("} else ")
                self.visit(node.orelse[0])
            else:
                self.emit("} else {")
                self.indent_inc()
                for stmt in node.orelse:
                    self.visit(stmt)
                self.indent_dec()
                self.emit("}")
        else:
            self.emit("}")

    def visit_While(self, node):
        cond = self.gen_condition(node.test)
        self.emit(f"while ({cond}) {{")
        self.indent_inc()
        for stmt in node.body:
            self.visit(stmt)
        self.indent_dec()
        self.emit("}")

    def visit_Break(self, node): self.emit("break;")
    def visit_Continue(self, node): self.emit("continue;")

    def visit_For(self, node):
        if isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Name) and node.iter.func.id == 'range':
            self._for_range(node)
        elif isinstance(node.iter, ast.Name):
            self._for_array(node)
        else:
            raise NotImplementedError("for только по range или массиву")

    def _for_range(self, node):
        call = node.iter
        args = call.args
        if len(args) == 1:
            _, stop_c = self.gen_expr(args[0])
            start_c, step_c = "0", "1"
        elif len(args) == 2:
            _, start_c = self.gen_expr(args[0])
            _, stop_c = self.gen_expr(args[1])
            step_c = "1"
        elif len(args) == 3:
            _, start_c = self.gen_expr(args[0])
            _, stop_c = self.gen_expr(args[1])
            _, step_c = self.gen_expr(args[2])
        else:
            raise ValueError("range 1-3 аргумента")
        loop_var = node.target.id
        self.var_types[loop_var] = 'int'
        self.emit(f"for (int {loop_var} = {start_c}; {loop_var} < {stop_c}; {loop_var} += {step_c}) {{")
        self.indent_inc()
        for stmt in node.body:
            self.visit(stmt)
        self.indent_dec()
        self.emit("}")

    def _for_array(self, node):
        arr_name = node.iter.id
        loop_var = node.target.id
        arr_type = self.var_types.get(arr_name, "int*")
        self.emit("for (int i = 0; i < len; i++) {")
        self.indent_inc()
        elem_type = "int" if "int" in arr_type else "double"
        self.var_types[loop_var] = elem_type
        self.emit(f"{elem_type} {loop_var} = {arr_name}[i];")
        for stmt in node.body:
            self.visit(stmt)
        self.indent_dec()
        self.emit("}")

    def visit_Return(self, node):
        if node.value is None:
            self.emit("return;")
        else:
            _, code = self.gen_expr(node.value)
            self.emit(f"return {code};")

    # print и input
    def visit_Expr(self, node):
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            if node.value.func.id == 'print':
                self._gen_print(node.value)
            elif node.value.func.id == 'input':
                self._gen_input_stmt(node.value)

    def _gen_print(self, call):
        args = call.args
        if not args:
            self.emit('printf("\\n");')
            return
        fmt_parts = []
        c_args = []
        for a in args:
            typ, code = self.gen_expr(a)
            if typ == 'int':
                fmt_parts.append("%d")
            elif typ == 'double':
                fmt_parts.append("%f")
            elif typ == 'char*':
                fmt_parts.append("%s")
            else:
                fmt_parts.append("%p")
            c_args.append(code)
        fmt_str = " ".join(fmt_parts) + "\\n"
        fmt_esc = fmt_str.replace('"', '\\"')
        if c_args:
            self.emit(f'printf("{fmt_esc}", {", ".join(c_args)});')
        else:
            self.emit(f'printf("{fmt_esc}");')

    def _gen_input_assign(self, target, call):
        if not isinstance(target, ast.Name):
            raise NotImplementedError("input() только в переменную")
        var = target.id
        # строковый input
        self.var_types[var] = 'char*'
        self.need_malloc = True
        self.emit(f'{var} = malloc(256);')
        if call.args:
            prompt = call.args[0]
            if isinstance(prompt, ast.Constant) and isinstance(prompt.value, str):
                self.emit(f'printf("{prompt.value}");')
        self.emit(f'fgets({var}, 256, stdin);')
        self.emit(f'{{ char *p = strchr({var}, \'\\n\'); if (p) *p = 0; }}')

    def _gen_input_stmt(self, call):
        dummy = "__dummy_input"
        if dummy not in self.var_types:
            self.var_types[dummy] = 'char*'
            self.need_malloc = True
            self.emit(f'char *{dummy} = malloc(256);')
        if call.args:
            prompt = call.args[0]
            if isinstance(prompt, ast.Constant) and isinstance(prompt.value, str):
                self.emit(f'printf("{prompt.value}");')
        self.emit(f'fgets({dummy}, 256, stdin);')
        self.emit(f'{{ char *p = strchr({dummy}, \'\\n\'); if (p) *p = 0; }}')

    # Генерация условий и выражений
    def gen_condition(self, node):
        if isinstance(node, ast.Compare):
            left_type, left_code = self.gen_expr(node.left)
            ops = node.ops
            comparators = node.comparators
            parts = []
            curr_left = left_code
            curr_type = left_type
            for op, right in zip(ops, comparators):
                right_type, right_code = self.gen_expr(right)
                if curr_type == 'char*' and right_type == 'char*':
                    if isinstance(op, ast.Eq):
                        parts.append(f"(strcmp({curr_left}, {right_code}) == 0)")
                    elif isinstance(op, ast.NotEq):
                        parts.append(f"(strcmp({curr_left}, {right_code}) != 0)")
                    elif isinstance(op, ast.Lt):
                        parts.append(f"(strcmp({curr_left}, {right_code}) < 0)")
                    elif isinstance(op, ast.LtE):
                        parts.append(f"(strcmp({curr_left}, {right_code}) <= 0)")
                    elif isinstance(op, ast.Gt):
                        parts.append(f"(strcmp({curr_left}, {right_code}) > 0)")
                    elif isinstance(op, ast.GtE):
                        parts.append(f"(strcmp({curr_left}, {right_code}) >= 0)")
                    else:
                        raise NotImplementedError(f"Сравнение строк {type(op)}")
                else:
                    op_str = self._cmp_op(op)
                    parts.append(f"({curr_left} {op_str} {right_code})")
                curr_left = right_code
                curr_type = right_type
            return " && ".join(parts)
        elif isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                join = " && "
            elif isinstance(node.op, ast.Or):
                join = " || "
            else:
                raise NotImplementedError(f"BoolOp {type(node.op)}")
            return join.join(f"({self.gen_condition(v)})" for v in node.values)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return f"(!{self.gen_condition(node.operand)})"
        else:
            _, code = self.gen_expr(node)
            return code

    def _cmp_op(self, op):
        m = {ast.Eq:"==", ast.NotEq:"!=", ast.Lt:"<", ast.LtE:"<=",
             ast.Gt:">", ast.GtE:">=", ast.Is:"==", ast.IsNot:"!="}
        return m.get(type(op), "??")

    def gen_expr(self, node):
        if isinstance(node, ast.Constant):
            val = node.value
            if isinstance(val, int): return ('int', str(val))
            if isinstance(val, float): return ('double', str(val))
            if isinstance(val, str): return ('char*', f'"{val.replace('"', '\\"')}"')
            if val is None: return ('void*', 'NULL')
            raise NotImplementedError(f"Константа {type(val)}")
        if isinstance(node, ast.Name):
            var = node.id
            if var not in self.var_types:
                self.var_types[var] = 'double'
            return (self.var_types[var], var)
        if isinstance(node, ast.BinOp):
            l_t, l_c = self.gen_expr(node.left)
            r_t, r_c = self.gen_expr(node.right)
            op = node.op
            if isinstance(op, ast.Add) and l_t == 'char*' and r_t == 'char*':
                raise NotImplementedError("Конкатенация строк только в присваивании")
            if isinstance(op, (ast.Div, ast.Pow)):
                res_t = 'double'
            elif isinstance(op, ast.FloorDiv):
                res_t = 'int' if (l_t == 'int' and r_t == 'int') else 'double'
            else:
                res_t = 'double' if (l_t == 'double' or r_t == 'double') else 'int'
            if isinstance(op, ast.Add): code = f"({l_c} + {r_c})"
            elif isinstance(op, ast.Sub): code = f"({l_c} - {r_c})"
            elif isinstance(op, ast.Mult): code = f"({l_c} * {r_c})"
            elif isinstance(op, ast.Div):
                if l_t == 'int' and r_t == 'int':
                    code = f"((double){l_c} / {r_c})"
                else:
                    code = f"({l_c} / {r_c})"
            elif isinstance(op, ast.FloorDiv):
                if res_t == 'int':
                    code = f"({l_c} / {r_c})"
                else:
                    code = f"floor({l_c} / {r_c})"
            elif isinstance(op, ast.Mod): code = f"({l_c} % {r_c})"
            elif isinstance(op, ast.Pow): code = f"pow({l_c}, {r_c})"
            else: raise NotImplementedError(f"BinOp {type(op)}")
            return (res_t, code)
        if isinstance(node, ast.Subscript):
            def get_base(node):
                if isinstance(node, ast.Subscript):
                    base, idxs = get_base(node.value)
                    _, idx_c = self.gen_expr(node.slice)
                    idxs.append(idx_c)
                    return base, idxs
                elif isinstance(node, ast.Name):
                    return node.id, []
                else:
                    raise NotImplementedError("Сложный доступ")
            arr_name, idx_list = get_base(node)
            if arr_name not in self.var_types:
                self.var_types[arr_name] = "int*"
            arr_type = self.var_types[arr_name]
            elem_type = "int" if ("int" in arr_type or arr_type.endswith('*')) else "double"
            if len(idx_list) == 1:
                code = f"{arr_name}[{idx_list[0]}]"
            else:
                code = f"{arr_name}[{']['.join(idx_list)}]"
            return (elem_type, code)
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.USub):
                t, c = self.gen_expr(node.operand)
                return (t, f"-{c}")
            if isinstance(node.op, ast.UAdd):
                return self.gen_expr(node.operand)
            raise NotImplementedError(f"UnaryOp {type(node.op)}")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == 'len':
                if len(node.args) == 1 and isinstance(node.args[0], ast.Name):
                    return ('int', 'len')
                else:
                    raise NotImplementedError("len() только от переменной")
            else:
                raise NotImplementedError(f"Вызов {node.func.id}")
        raise NotImplementedError(f"Выражение {type(node)}")