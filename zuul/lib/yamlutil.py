import yaml
try:
    from yaml import cyaml
    import _yaml
    SafeLoader = yaml.CSafeLoader
    Dumper = yaml.CDumper
    Mark = _yaml.Mark
except ImportError:
    SafeLoader = yaml.SafeLoader
    Dumper = yaml.Dumper
    Mark = yaml.Mark
