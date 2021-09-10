from ruamel.yaml import YAML
from ..types import ID, Attachment


def get_yaml():
    yaml = YAML(typ='safe')
    yaml.width = 120
    yaml.default_flow_style = False
    yaml.register_class(ID)
    yaml.register_class(Attachment)
    return yaml
