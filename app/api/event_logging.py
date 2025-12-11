"""
事件日志接口路由
"""
import uuid
import logging
from fastapi import APIRouter, Request

from app.models import EventLoggingBatchResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/event_logging/batch")
async def event_logging_batch(request: Request):
    """批量事件日志记录接口"""
    try:
        try:
            body = await request.json()
        except:
            body = {}
        
        batch_id = body.get("batch_id") or f"batch_{uuid.uuid4().hex[:16]}"

        
        events = body.get("events", [])
        if not isinstance(events, list):
            events = [events] if events else []
        
        processed_count = len(events)
        
        if events:
            logger.debug(f"📝 Event Logging Batch: batch_id={batch_id}, events_count={processed_count}")
            for i, event in enumerate(events[:5]):
                event_type = event.get("event_type", "unknown") if isinstance(event, dict) else "unknown"
                logger.debug(f"   Event {i+1}: type={event_type}")
            if processed_count > 5:
                logger.debug(f"   ... and {processed_count - 5} more events")
        
        return EventLoggingBatchResponse(
            success=True,
            batch_id=batch_id,
            processed_count=processed_count,
            message="Events logged successfully"
        )
        
    except Exception as e:
        logger.warning(f"Event logging batch error: {e}")
        return EventLoggingBatchResponse(
            success=True,
            batch_id=f"batch_{uuid.uuid4().hex[:16]}",
            processed_count=0,
            message="Events received"
        )

