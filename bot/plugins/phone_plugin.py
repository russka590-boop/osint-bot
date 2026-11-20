from __future__ import annotations

from bot.core.plugin import Finding, OSINTPlugin, PluginResult, TargetKind, register

TYPE_NAMES = {
    "MOBILE": "мобильный",
    "FIXED_LINE": "стационарный",
    "FIXED_LINE_OR_MOBILE": "стационарный или мобильный",
    "TOLL_FREE": "бесплатный",
    "PREMIUM_RATE": "платный",
    "SHARED_COST": "с раздельной оплатой",
    "VOIP": "VoIP",
    "PERSONAL_NUMBER": "личный",
    "PAGER": "пейджер",
    "UAN": "UAN",
    "VOICEMAIL": "голосовая почта",
    "UNKNOWN": "неизвестен",
}


def type_name(phonenumbers, number_type: int) -> str:
    for name, title in TYPE_NAMES.items():
        if getattr(phonenumbers.PhoneNumberType, name, None) == number_type:
            return title
    return "неизвестен"


class PhonePlugin(OSINTPlugin):
    name = "phone"
    title = "Телефон: страна, оператор, регион"
    description = "Определяет страну, оператора и регион по номеру. Владельца номера не ищет."
    input_types = (TargetKind.PHONE,)
    default_timeout = 20

    async def ready(self) -> tuple[bool, str]:
        try:
            import phonenumbers  # noqa: F401
        except ImportError:
            return False, "pip install phonenumbers"
        return True, ""

    async def run(self, target: str) -> PluginResult:
        import phonenumbers
        from phonenumbers import carrier, geocoder

        result = PluginResult(plugin=self.name, title=self.title, target=target)
        try:
            number = phonenumbers.parse(target, None)
        except phonenumbers.NumberParseException as exc:
            result.ok = False
            result.errors.append(f"номер не разобран: {exc}")
            return result

        if not phonenumbers.is_valid_number(number):
            result.findings.append(
                Finding(
                    source="Номер",
                    status="not_found",
                    details="номер невалиден по международному плану нумерации",
                )
            )
            return result

        details = [
            f"страна: {phonenumbers.region_code_for_number(number) or '—'}",
            f"оператор: {carrier.name_for_number(number, 'ru') or '—'}",
            f"регион: {geocoder.description_for_number(number, 'ru') or '—'}",
            f"тип: {type_name(phonenumbers, phonenumbers.number_type(number))}",
        ]

        result.findings.append(
            Finding(
                source="Номер",
                status="found",
                details=" · ".join(details),
            )
        )
        return result


register(PhonePlugin())
