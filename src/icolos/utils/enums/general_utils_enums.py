class CheckFileGenerationEnum:

    GENERATED_SUCCESS = "generated_success"
    GENERATED_EMPTY = "generated_empty"
    NOT_GENERATED = "not_generated"

    # try to find the internal value and return
    def __getattr__(self, name):
        if name in self:
            return name
        raise AttributeError

    # prohibit any attempt to set any values
    def __setattr__(self, key, value):
        raise ValueError("No changes allowed.")
