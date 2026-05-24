# #services/artifact_service.py
# from datetime import datetime, timezone
# from database.models import Artifact

# class ArtifactService:
#     """Responsible for
#     - fetch_remote_file
#     - Artifact DB
#     - signed URLs
#     """
#     def __init__(self,db_session_factory):
#         self.db=db_session_factory

#     async def store_artifact(
#             self,
#             invocation_id,
#             file_id,
#             filename,
#             signed_url,
#             path
#     ):
#         async with self.db() as db:
#             artifact=Artifact(
#                 invocation_id=invocation_id,
#                 file_id=file_id,
#                 filename=filename,
#                 url=signed_url,
#                 path=str(path),
#                 created_at=datetime.now(timezone.utc)
#             )
            
#             db.add(artifact)
#             await db.commit()


# services/artifact_service.py

from datetime import datetime, timezone
from database.models import Artifact

class ArtifactService:
    """
    Responsible for:
    - Persisting artifacts (uploads & generated files)
    - Ownership enforcement (tenant/user/session)
    """

    def __init__(self, db_session_factory):
        self.db = db_session_factory

    async def store_artifact(
        self,
        *,
        tenant_id: str,
        user_id: str,
        session_id: str,
        file_id: str,
        filename: str,
        signed_url: str,
        path: str,
        invocation_id: int | None = None,
        mime_type: str | None = None,
        file_size: int | None = None,
    ):
        """
        Stores an artifact in a fully user-scoped manner.

        invocation_id:
          - None for uploads (pre-agent)
          - Set later for generated artifacts
        """
        async with self.db() as db:
            artifact = Artifact(
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                invocation_id=invocation_id,
                file_id=file_id,
                filename=filename,
                url=signed_url,
                path=str(path),
                mime_type=mime_type,
                file_size=file_size,
                created_at=datetime.now(timezone.utc),
            )

            db.add(artifact)
            await db.commit()
            await db.refresh(artifact)

            return artifact