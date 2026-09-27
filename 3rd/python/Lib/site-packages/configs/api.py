from .config import Config

def load(config_file):
    """Constructs and returns a :class:`Config <Config>` instance.

    :param config_file: configuration file to be parsed

    Usage::

        >>> import configs

        >>> fc = configs.load('sample.conf')

        >>> fc['general']['spam']
        eggs
    """

    return Config(config_file)
