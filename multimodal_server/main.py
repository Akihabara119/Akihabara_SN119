from fastapi import FastAPI, HTTPException
import base_model
import inference
import traceback
from typing import Callable
from functools import wraps
from model_manager import model_manager
from starlette.responses import PlainTextResponse
from loguru import logger
import base64
import io
from PIL import Image
import asyncio
import threading
import time
import json
import os
from dotenv import load_dotenv

from service_manager import create_service_manager, ServiceManager

load_dotenv('.multimodal_server.env')

safety_checker = None

service_manager: ServiceManager = None
service_thread: threading.Thread = None


def start_backend_services():
    global service_manager, service_thread

    def run_services():
        global service_manager
        try:
            config = {
                'work_dir': os.getenv('WORK_DIR', './workspace'),
                'comfyui': {
                    'host': os.getenv('COMFYUI_HOST', '127.0.0.1'),
                    'port': int(os.getenv('COMFYUI_PORT', '8188'))
                }
            }

            service_manager = create_service_manager(config)

            if service_manager.start_all_services():
                logger.info("Backend services started successfully")

                while service_manager.running:
                    time.sleep(1)

                    if not service_manager.check_service_health():
                        logger.error("Service health check failed")
                        break
            else:
                logger.error("Failed to start backend services")

        except Exception as e:
            logger.error(f"Service thread error: {e}")

    service_thread = threading.Thread(target=run_services, daemon=True)
    service_thread.start()

    time.sleep(10)


def stop_backend_services():
    global service_manager
    if service_manager:
        service_manager.stop_all_services()


app = FastAPI(title="Multimodal Server", version="1.0.0")

def handle_request_errors(func: Callable):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            tb_str = traceback.format_exc()
            logger.error(f"Error in {func.__name__}: {str(e)}\n{tb_str}")
            if 'no face detected' in str(e).lower():
                raise HTTPException(status_code=400, detail={"error": str(e), "traceback": tb_str})
            else:
                raise HTTPException(status_code=500, detail={"error": str(e), "traceback": tb_str})

    return wrapper


@app.get("/")
async def home():
    return PlainTextResponse("Image!")


@app.post("/load_model")
@handle_request_errors
async def load_model(request_data: base_model.LoadModelRequest) -> base_model.LoadModelResponse:
    return await model_manager.download_model(request_data)


@app.post("/text-to-image")
@handle_request_errors
async def text_to_image(request_data: base_model.TextToImageBase) -> base_model.ImageResponseBody:
    return await inference.text_to_image_infer(request_data)


# @handle_request_errors
@app.post("/image-to-image")
async def image_to_image(request_data: base_model.ImageToImageBase) -> base_model.ImageResponseBody:
    return await inference.image_to_image_infer(request_data)


@app.post("/upscale")
@handle_request_errors
async def upscale(request_data: base_model.UpscaleBase) -> base_model.ImageResponseBody:
    return await inference.upscale_infer(request_data)


@app.post("/inpaint")
@handle_request_errors
async def inpaint(
        request_data: base_model.InpaintingBase,
) -> base_model.ImageResponseBody:
    return await inference.inpainting_infer(request_data)


@app.post("/outpaint")
@handle_request_errors
async def outpaint(
        request_data: base_model.OutpaintingBase,
) -> base_model.ImageResponseBody:
    return await inference.outpainting_infer(request_data)


@app.post("/clip-embeddings")
@handle_request_errors
async def clip_embeddings(
        request_data: base_model.ClipEmbeddingsBase,
) -> base_model.ClipEmbeddingsResponse:
    embeddings = await inference.get_clip_embeddings(request_data)
    return base_model.ClipEmbeddingsResponse(clip_embeddings=embeddings)


@app.post("/clip-embeddings-text")
@handle_request_errors
async def clip_embeddings_text(
        request_data: base_model.ClipEmbeddingsTextBase,
) -> base_model.ClipEmbeddingsTextResponse:
    embedding = await inference.get_clip_embeddings_text(request_data)
    return base_model.ClipEmbeddingsTextResponse(text_embedding=embedding)


@app.post("/check-nsfw")
@handle_request_errors
async def check_nsfw(
        request_data: base_model.CheckNSFWBase,
) -> base_model.CheckNSFWResponse:
    global safety_checker

    if safety_checker is None:
        try:
            from utils import safety_checker as sc
            safety_checker = sc.Safety_Checker()
            logger.info("Safety checker initialized on first use")
        except Exception as e:
            logger.error(f"Failed to initialize safety checker: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to initialize safety checker: {str(e)}")

    try:
        if request_data.image.startswith('data:image'):
            base64_data = request_data.image.split(',')[1]
        else:
            base64_data = request_data.image
        image_bytes = base64.b64decode(base64_data)
        image = Image.open(io.BytesIO(image_bytes))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image data: {str(e)}")

    is_nsfw = safety_checker.nsfw_check(image)
    return base_model.CheckNSFWResponse(is_nsfw=is_nsfw)


@app.get("/service-status")
async def get_service_status():
    global service_manager
    if service_manager:
        return service_manager.get_service_status()
    else:
        return {"running": False, "services": {}}


if __name__ == "__main__":
    import uvicorn
    import os
    import argparse
    import signal
    import sys

    parser = argparse.ArgumentParser(description='Multimodal Server')
    parser.add_argument('--host', default='0.0.0.0', help='Server host')
    parser.add_argument('--port', type=int, default=6919, help='Server port')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--start-services', action='store_true', help='Start backend services (ComfyUI and vLLM)')

    args = parser.parse_args()

    if "CUBLAS_WORKSPACE_CONFIG" not in os.environ:
        os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"

    import torch

    torch.use_deterministic_algorithms(False)


    def signal_handler(signum, frame):
        stop_backend_services()
        sys.exit(0)


    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    start_services = args.start_services or os.getenv('START_BACKEND_SERVICES', 'false').lower() == 'true'

    if start_services:
        start_backend_services()

        import time

        comfyui_ready = False
        comfyui_host = os.getenv('COMFYUI_HOST', '127.0.0.1')
        comfyui_port = os.getenv('COMFYUI_PORT', '8188')
        for i in range(30):
            try:
                import requests

                response = requests.get(f"http://{comfyui_host}:{comfyui_port}", timeout=5)
                if response.status_code == 200:
                    logger.info("ComfyUI service is ready!")
                    comfyui_ready = True
                    break
            except:
                pass
            time.sleep(2)
            if i % 5 == 0:
                logger.info(f"Still waiting for ComfyUI service... ({i * 2}s)")

        if not comfyui_ready:
            logger.warning("ComfyUI service may not be ready, but continuing...")

        if comfyui_ready:
            logger.info("Initializing WebSocket connections...")
            try:
                from utils.api_gate import initialize_websocket

                initialize_websocket()
                logger.info("WebSocket connections initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize WebSocket connections: {e}")
        else:
            logger.warning("Skipping WebSocket initialization due to ComfyUI not ready")
    else:
        logger.info("Skipping backend services startup")

    try:
        uvicorn.run(app, host=args.host, port=args.port)
    finally:
        stop_backend_services()
