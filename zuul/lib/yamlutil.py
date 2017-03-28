import yaml
try:
    from yaml import cyaml
    yaml.SafeLoader = cyaml.CSafeLoader
    yaml.Dumper = cyaml.CDumper
except ImportError:
    pass
