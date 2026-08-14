"""Interactive CLI for Zeus."""

import argparse
import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory

from zeus.core.agent import run_agent, run_summary
from zeus.core.team import create_default_team, Team, Worker
from zeus.memory.session_log import get_logger
from zeus.tools import terminal, file, web, memory_tools, sandbox_client, sandbox, git, code_execution, browser, database, scheduler  # noqa: F401


def main() -> None:
    parser = argparse.ArgumentParser(description="Zeus Agent Harness")
    parser.add_argument("-q", "--query", help="Single query, non-interactive")
    parser.add_argument("--session", help="Session ID for logging")
    parser.add_argument("--summary", action="store_true", help="Print session summary after query")
    parser.add_argument("--team", action="store_true", help="Use multi-agent team orchestration")
    parser.add_argument("gateway", nargs=argparse.REMAINDER, help="Gateway commands (start/setup)")
    args = parser.parse_args()

    if args.gateway:
        from zeus.gateway.cli import main as gateway_main
        sys.argv = ["zeus-gateway"] + args.gateway[1:]
        gateway_main()
        return

    logger = get_logger(args.session)

    if args.query:
        logger.log_turn("user", args.query)
        if args.team:
            team = create_default_team(session_id=logger.session_id)
            response = team.run(args.query)
        else:
            response = run_agent(args.query, session_id=logger.session_id)
        logger.log_turn("assistant", response)
        print(response)
        if args.summary:
            print("\n--- Session summary ---")
            print(run_summary(session_id=logger.session_id))
        return

    session = PromptSession(history=FileHistory(".zeus_history"))
    print(f"Zeus Agent Harness v0.1.0 (session: {logger.session_id})")
    print("Digite /new para nova sessão, /sair para encerrar.\n")

    while True:
        try:
            user_input = session.prompt("zeus> ")
        except (EOFError, KeyboardInterrupt):
            print("\nSaindo...")
            break

        text = user_input.strip()
        if not text:
            continue
        if text in ("/sair", "/quit", "/exit"):
            print("Saindo...")
            break
        if text == "/new":
            logger = get_logger(new_session=True)
            print(f"Nova sessão: {logger.session_id}\n")
            continue

        logger.log_turn("user", text)
        try:
            if text.startswith("/team "):
                team = create_default_team(session_id=logger.session_id)
                response = team.run(text[len("/team "):])
            else:
                response = run_agent(text, session_id=logger.session_id)
            logger.log_turn("assistant", response)
            print(response)
        except Exception as e:
            logger.log_turn("error", str(e))
            print(f"Erro: {e}", file=sys.stderr)

    print(f"Session log: {logger.log_path}")
    print(run_summary(session_id=logger.session_id))


if __name__ == "__main__":
    main()
