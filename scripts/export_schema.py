"""Write the JSON schemas to schema/ (model_output, image_result, gold_label)."""
import _path  # noqa: F401
from damagevision.schema import export_schemas

if __name__ == "__main__":
    for p in export_schemas("schema"):
        print("wrote", p)
