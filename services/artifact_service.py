#services/artifact_service.py
from datetime import datetime, timezone
from database.models import Artifact

class ArtifactService:
    """Responsible for
    - fetch_remote_file
    - Artifact DB
    - signed URLs
    """
    def __init__(self,db_session_factory):
        self.db=db_session_factory

    async def store_artifact(
            self,
            invocation_id,
            file_id,
            filename,
            signed_url,
            path
    ):
        async with self.db() as db:
            artifact=Artifact(
                invocation_id=invocation_id,
                file_id=file_id,
                filename=filename,
                url=signed_url,
                path=str(path),
                created_at=datetime.now(timezone.utc)
            )
            
            db.add(artifact)
            await db.commit()