import asyncio

from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai.types import Content, Part

from agents.agent import root_agent


async def main():

    session_service = InMemorySessionService()

    # ---- FIX: Create session before running ----
    session=await session_service.create_session(
        app_name="testing_app",
        user_id="adit1234",
        session_id="default-session",
    )

    runner = Runner(
        app_name="testing_app",
        agent=root_agent,
        session_service=session_service,
    )

    msg = Content(role="user", parts=[Part(text="How are you?")])

    print("Running agent...\n")

    final_response = None

    async for event in runner.run_async(
        user_id="adit1234",
        session_id="default-session",
        new_message=msg,
    ):
        # Print all events to inspect
        print("EVENT:", event)

        # Try to detect the finalized model output event
        # Your SDK usually produces something like:
        #   event.type == "message.completed"
        #   or event.output / event.delta
        # if hasattr(event, "output"):

            # final_response = event.output
        if getattr(event,'content',None) and getattr(event.content,'parts',None):
            print("parts: ", event.content.parts)
            print('INPUT TOKEN:',event.usage_metadata.prompt_token_count)
            print('OUTPUT TOKEN:',event.usage_metadata.candidates_token_count)
            print('TOTAL TOKEN COUNT:', event.usage_metadata.total_token_count)




    print("\n=========== FINAL RESPONSE ===========")
    print(final_response)
    print("======================================\n")


if __name__ == "__main__":
    asyncio.run(main())