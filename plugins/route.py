import re
import math
import logging
import secrets
import mimetypes
import time
import asyncio # Added for better async handling

from info import URL, MULTI_CLIENT # Assuming URL and MULTI_CLIENT are in info.py
from aiohttp import web
from aiohttp.http_exceptions import BadStatusLine
from TechVJ.bot import multi_clients, work_loads, TechVJBot # Ensure TechVJBot is your main bot instance
from TechVJ.server.exceptions import FIleNotFound, InvalidHash
from TechVJ import StartTime, __version__ # Assuming these are defined in TechVJ/__init__.py
from TechVJ.util.custom_dl import ByteStreamer
from TechVJ.util.time_format import get_readable_time
from TechVJ.util.render_template import render_page # For watch/ stream HTML page
from TechVJ.util.file_properties import get_name, get_hash # Import if needed for logs/security

# Configure logging for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO) # Set appropriate logging level

routes = web.RouteTableDef()

@routes.get("/", allow_head=True)
async def root_route_handler(request):
    """Handles the root route, displaying bot status."""
    uptime = get_readable_time(time.time() - StartTime)
    response_text = f"My Server is Running!\n\nBot Version: {__version__}\nUptime: {uptime}"
    return web.Response(text=response_text, content_type='text/plain')

@routes.get(r"/watch/{path:\S+}", allow_head=True)
async def stream_page_handler(request: web.Request):
    """
    Handles requests for the HTML streaming page.
    Path format: /watch/{secure_hash}{file_id} or /watch/{file_id}?hash={secure_hash}
    """
    try:
        file_id, secure_hash = await extract_file_details(request)
        if not file_id or not secure_hash:
            raise web.HTTPBadRequest(text="Invalid URL format or missing hash.")

        # Render the HTML page for watching
        return web.Response(text=await render_page(file_id, secure_hash), content_type='text/html')

    except InvalidHash as e:
        logger.warning(f"Attempted access with invalid hash: {e.message}")
        raise web.HTTPForbidden(text=e.message)
    except FIleNotFound as e:
        logger.warning(f"File not found for ID {file_id}: {e.message}")
        raise web.HTTPNotFound(text=e.message)
    except web.HTTPError: # Catch specific HTTP errors raised by self
        raise
    except Exception as e:
        logger.exception(f"Unhandled error in stream_page_handler for path {request.path}: {e}")
        raise web.HTTPInternalServerError(text="An internal server error occurred.")

@routes.get(r"/{path:\S+}", allow_head=True)
async def file_stream_handler(request: web.Request):
    """
    Handles direct file streaming/download requests.
    Path format: /{secure_hash}{file_id} or /{file_id}?hash={secure_hash}
    """
    try:
        file_id, secure_hash = await extract_file_details(request)
        if not file_id or not secure_hash:
            raise web.HTTPBadRequest(text="Invalid URL format or missing hash.")

        return await media_streamer(request, file_id, secure_hash)

    except InvalidHash as e:
        logger.warning(f"Attempted direct access with invalid hash: {e.message}")
        raise web.HTTPForbidden(text=e.message)
    except FIleNotFound as e:
        logger.warning(f"File not found for ID {file_id}: {e.message}")
        raise web.HTTPNotFound(text=e.message)
    except web.HTTPError: # Catch specific HTTP errors raised by self
        raise
    except (AttributeError, BadStatusLine, ConnectionResetError):
        logger.info(f"Client disconnected during streaming for path {request.path}")
        # These are common client-side disconnections, no need to raise HTTP 500
    except Exception as e:
        logger.exception(f"Unhandled error in file_stream_handler for path {request.path}: {e}")
        raise web.HTTPInternalServerError(text="An internal server error occurred during streaming.")

async def extract_file_details(request: web.Request):
    """
    Helper function to extract file ID and secure hash from the request path or query.
    Supports both /hash_id and /id?hash=hash_value formats.
    """
    path = request.match_info["path"]
    secure_hash = request.rel_url.query.get("hash")
    file_id = None

    # Try to match the combined hash+id format first (e.g., /abcde123456)
    match_combined = re.search(r"^([a-zA-Z0-9_-]{6})(\d+)$", path)
    if match_combined:
        secure_hash_from_path = match_combined.group(1)
        file_id_from_path = int(match_combined.group(2))
        
        # If hash is provided in query, prioritize it for flexibility, else use from path
        if secure_hash and secure_hash_from_path and secure_hash != secure_hash_from_path:
            logger.warning(f"Hash mismatch: Query hash '{secure_hash}' vs Path hash '{secure_hash_from_path}' for ID {file_id_from_path}")
            # Decide on policy: raise error, or prioritize one. For now, prioritize query if present.
            # If you always want combined format to be authoritative, remove this check.
        
        if not secure_hash: # If no query hash, use path hash
             secure_hash = secure_hash_from_path
        file_id = file_id_from_path
    else:
        # Fallback to the /id format with hash in query (e.g., /123456?hash=abcde)
        match_id_only = re.search(r"(\d+)(?:\/\S+)?", path)
        if match_id_only:
            file_id = int(match_id_only.group(1))

    return file_id, secure_hash

class_cache = {}

async def media_streamer(request: web.Request, file_id: int, secure_hash: str):
    """
    Streams the media content to the client.
    Handles range requests for partial content and resume.
    """
    range_header = request.headers.get("Range", None)
    
    # Select the client with the least workload
    index = min(work_loads, key=work_loads.get)
    faster_client = multi_clients[index]
    
    if MULTI_CLIENT:
        logger.info(f"Client {index} is now serving {request.remote} for file ID {file_id}")

    # Use cached ByteStreamer object or create a new one
    if faster_client not in class_cache:
        logger.debug(f"Creating new ByteStreamer object for client {index}")
        tg_connect = ByteStreamer(faster_client)
        class_cache[faster_client] = tg_connect
    else:
        tg_connect = class_cache[faster_client]
        logger.debug(f"Using cached ByteStreamer object for client {index}")
    
    file_properties = await tg_connect.get_file_properties(file_id)
    
    # Hash validation
    if file_properties.unique_id[:6] != secure_hash:
        logger.warning(f"Security Alert: Invalid hash '{secure_hash}' for message with ID {file_id}. Expected: {file_properties.unique_id[:6]}")
        raise InvalidHash("Provided hash is invalid. Access Denied.")
    
    file_size = file_properties.file_size
    mime_type = file_properties.mime_type
    file_name = file_properties.file_name

    # Determine disposition
    # force_download = request.rel_url.query.get("download", "false").lower() == "true"
    # disposition = "attachment" if force_download else "inline"
    disposition = "attachment" # Default to attachment for direct download links

    if mime_type:
        if not file_name:
            try:
                # Fallback filename if not available
                file_name = f"{secrets.token_hex(2)}.{mime_type.split('/')[1]}"
            except (IndexError, AttributeError):
                file_name = f"{secrets.token_hex(2)}.unknown"
    else:
        if file_name:
            mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        else:
            mime_type = "application/octet-stream"
            file_name = f"{secrets.token_hex(2)}.unknown"

    from_bytes = 0
    until_bytes = file_size - 1
    status_code = 200 # Default to 200 OK

    if range_header:
        status_code = 206 # Partial Content
        try:
            # Parse range header (e.g., "bytes=0-100" or "bytes=100-")
            range_parts = range_header.replace("bytes=", "").split("-")
            from_bytes = int(range_parts[0])
            if len(range_parts) > 1 and range_parts[1]:
                until_bytes = int(range_parts[1])
            else:
                until_bytes = file_size - 1 # If end not specified, range till end

            if not (0 <= from_bytes < file_size and 0 <= until_bytes < file_size and from_bytes <= until_bytes):
                logger.warning(f"Invalid range header '{range_header}' for file ID {file_id}")
                return web.Response(
                    status=416,
                    body="416: Range Not Satisfiable",
                    headers={"Content-Range": f"bytes */{file_size}"},
                )
        except ValueError:
            logger.warning(f"Malformed range header '{range_header}' for file ID {file_id}")
            # If range header is malformed, treat as a regular 200 request or error
            status_code = 200
            from_bytes = 0
            until_bytes = file_size - 1

    req_length = until_bytes - from_bytes + 1
    
    chunk_size = 1024 * 1024 # 1MB chunk size
    offset = from_bytes - (from_bytes % chunk_size) # Align offset to chunk boundary
    first_part_cut = from_bytes - offset # How much to cut from the first chunk
    
    # Calculate how much of the last chunk to send
    # This ensures only the requested bytes are sent, even if the last chunk is partial
    last_part_offset_in_chunk = (until_bytes + 1) % chunk_size # How many bytes needed from the last chunk
    last_part_cut = last_part_offset_in_chunk if last_part_offset_in_chunk != 0 else chunk_size
    
    # Total number of chunks involved in the request
    # math.ceil((until_bytes + 1 - offset) / chunk_size)
    part_count = (until_bytes // chunk_size) - (offset // chunk_size) + 1


    body = tg_connect.yield_file(
        file_properties, index, offset, first_part_cut, last_part_cut, part_count, chunk_size
    )

    headers = {
        "Content-Type": mime_type,
        "Content-Range": f"bytes {from_bytes}-{until_bytes}/{file_size}",
        "Content-Length": str(req_length),
        "Content-Disposition": f'{disposition}; filename="{file_name}"',
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-cache, no-store, must-revalidate", # Prevent aggressive caching of partial content
        "Pragma": "no-cache",
        "Expires": "0"
    }

    return web.Response(
        status=status_code,
        body=body,
        headers=headers,
    )

