from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from .nodes import (
    VSTLoader,
    VSTInspector,
    VSTManualParameters,
    VSTParameters,
    VSTApplyEffect,
)

WEB_DIRECTORY = "./js"


class VSTExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            VSTLoader,
            VSTInspector,
            VSTManualParameters,
            VSTParameters,
            VSTApplyEffect,
        ]


async def comfy_entrypoint() -> VSTExtension:
    return VSTExtension()
