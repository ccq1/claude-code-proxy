"""
插件市场与插件运行时配置接口
"""
from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.plugin_marketplace import (
    build_plugin_bundle,
    build_plugin_runtime_config,
    get_plugin_asset_path,
    get_plugin_manifest,
    list_plugins,
)
from app.plugin_marketplace.store import guess_asset_media_type

router = APIRouter()


@router.get("/plugins/list")
async def get_plugin_list():
    return list_plugins()


@router.get("/plugins/{plugin_name}/manifest")
async def get_plugin_manifest_info(plugin_name: str):
    return get_plugin_manifest(plugin_name)


@router.get("/plugins/{plugin_name}/download")
async def download_plugin_bundle(plugin_name: str):
    return build_plugin_bundle(plugin_name)


@router.get("/plugins/{plugin_name}/assets/{asset_path:path}")
async def get_plugin_asset(plugin_name: str, asset_path: str):
    asset = get_plugin_asset_path(plugin_name, asset_path)
    return FileResponse(asset, media_type=guess_asset_media_type(asset_path))


@router.get("/plugins/{plugin_name}")
async def get_plugin_config(plugin_name: str):
    """返回插件所需的运行时配置。"""
    return build_plugin_runtime_config(plugin_name)
