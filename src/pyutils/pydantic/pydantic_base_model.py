import abc
import json
import warnings

from .. import logging
import yaml
from pydantic import BaseModel as PydanticBaseModel

_logger = logging.getLogger()


class BaseModel(PydanticBaseModel, abc.ABC):
    # model_config = {
    #     'arbitrary_types_allowed': True,
    # }

    def to_dict(self, **kwargs) -> dict:
        return json.loads(self.model_dump_json(**kwargs))

    def to_yaml(self, dict_kwargs: dict | None = None, **kwargs) -> str:
        if dict_kwargs is None:
            dict_kwargs = {}
        return yaml.dump(self.to_dict(**dict_kwargs), sort_keys=False, indent=2, **kwargs).strip()

    def to_yaml_code_block(self, **kwargs) -> str:
        return f"```yaml\n{self.to_yaml(**kwargs)}\n```"

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(**kwargs))


class DeprecatedModel(BaseModel):
    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **kwargs):
        class_name = self.__class__.__name__
        message = (
            f"The use of `{class_name}` is discouraged.  Please consider an alternative approach."
        )
        _logger.warning(message)
        warnings.warn(message, category=UserWarning, stacklevel=2)
        super().__init__(**kwargs)
