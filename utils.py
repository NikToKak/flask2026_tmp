import ast
from translator import PyToCTranslator

def process_python_to_c(source_code: str) -> str:
    try:
        tree = ast.parse(source_code)
        translator = PyToCTranslator()
        c_code = translator.translate(tree)
        return c_code
    except Exception as e:
        return f"// Translation error: {str(e)}"