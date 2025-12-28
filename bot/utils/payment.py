from aiogram.types import LabeledPrice
from bot.config import SUBSCRIPTION_COST_MONTHLY, SUBSCRIPTION_COST_LIFETIME


def get_subscription_invoice(subscription_type: str) -> tuple[list[LabeledPrice], int]:
    """
    Получить детали счета для подписки.
    
    Args:
        subscription_type: 'monthly' или 'lifetime'
    
    Returns:
        Кортеж (цены, итоговая сумма в kopejkas)
    """
    
    if subscription_type == 'monthly':
        prices = [
            LabeledPrice(label="Подписка на месяц", amount=SUBSCRIPTION_COST_MONTHLY * 100)
        ]
        total = SUBSCRIPTION_COST_MONTHLY * 100
    
    elif subscription_type == 'lifetime':
        prices = [
            LabeledPrice(label="u041fожизненная подписка", amount=SUBSCRIPTION_COST_LIFETIME * 100)
        ]
        total = SUBSCRIPTION_COST_LIFETIME * 100
    
    else:
        return [], 0
    
    return prices, total


def get_subscription_price(subscription_type: str) -> int:
    """
    Получить цену подписки в Stars.
    """
    if subscription_type == 'monthly':
        return SUBSCRIPTION_COST_MONTHLY
    elif subscription_type == 'lifetime':
        return SUBSCRIPTION_COST_LIFETIME
    return 0


def get_subscription_duration(subscription_type: str) -> str:
    """
    Получить описание длительности подписки.
    """
    if subscription_type == 'monthly':
        return '30 дней'
    elif subscription_type == 'lifetime':
        return 'Пожизненно'
    return ''
