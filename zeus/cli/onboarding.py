"""First-run terminal onboarding for the Zeus CLI."""

from zeus.cli.setup_commands import _get_input, setup_model
from zeus.gateway.setup import setup_discord, setup_instagram, setup_telegram, setup_whatsapp

_CHANNEL_SETUP = {
    "whatsapp": setup_whatsapp,
    "instagram": setup_instagram,
    "telegram": setup_telegram,
    "discord": setup_discord,
}


def run_setup_wizard() -> bool:
    """Configure the model/provider and selected messaging integrations locally."""
    print("\n=== Configuração inicial do Zeus ===")
    print("As credenciais são digitadas apenas neste terminal, em prompts mascarados.\n")
    if not setup_model():
        return False

    print("\nIntegrações disponíveis: whatsapp, instagram, telegram, discord")
    print("Digite uma ou mais, separadas por vírgula; deixe vazio para configurar depois.")
    raw_selection = _get_input("Integrações")
    selected = [item.strip().lower() for item in raw_selection.split(",") if item.strip()]
    invalid = [item for item in selected if item not in _CHANNEL_SETUP]
    if invalid:
        print(f"Integração(ões) desconhecida(s): {', '.join(invalid)}")
        return False

    for channel in selected:
        if not _CHANNEL_SETUP[channel]():
            print(f"Configuração de {channel} cancelada ou incompleta.")
            return False

    print("\nConfiguração do Zeus concluída.")
    if "whatsapp" in selected:
        print("Para WhatsApp, inicie a ponte Baileys e escaneie o QR antes do gateway.")
    if "instagram" in selected:
        print("Instagram requer webhook HTTPS público e a inscrição do campo `messages` no app Meta.")
    return True
