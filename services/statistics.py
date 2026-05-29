from __future__ import annotations

from database.db import Database


class StatisticsService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def summary_text(self) -> str:
        summary = self.db.stats_summary()
        pairs = self.db.stats_by_pair()

        lines = [
            "📊 Статистика сигналов",
            "",
            f"Всего сигналов: {summary['total']}",
            f"WIN: {summary['win']} ✅",
            f"LOSS: {summary['loss']} ❌",
            f"DRAW: {summary['draw']} ➖",
            f"Винрейт: {summary['winrate']:.2f}%",
            f"Средняя сила WIN: {summary['avg_win_strength']:.2f}",
            f"Средняя сила LOSS: {summary['avg_loss_strength']:.2f}",
            "",
            "По парам:",
        ]

        if not pairs:
            lines.append("Пока нет записей.")
            return "\n".join(lines)

        for item in pairs[:15]:
            lines.append(
                f"{item['symbol']}: total={item['total']} | "
                f"W={item['win']} L={item['loss']} D={item['draw']} | "
                f"WR={item['winrate']:.1f}% | AVG_S={item['avg_strength']:.2f}"
            )

        return "\n".join(lines)

    def pairs_text(self) -> str:
        pairs = self.db.pair_leaderboard()
        lines = ["🏆 Лидеры пар", ""]
        if not pairs:
            lines.append("Пока нет завершенных сигналов.")
            return "\n".join(lines)

        for index, item in enumerate(pairs[:20], start=1):
            lines.append(
                f"{index}. {item['symbol']} | total={item['total']} | "
                f"W={item['win']} L={item['loss']} D={item['draw']} | "
                f"WR={item['winrate']:.1f}% | AVG_S={item['avg_strength']:.2f}"
            )
        return "\n".join(lines)
