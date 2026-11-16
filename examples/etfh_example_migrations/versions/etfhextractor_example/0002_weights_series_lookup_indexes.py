"""Give the example's signal and portfolio weights instances an index that leads with the series.

ms-markets 3.8.1 declares ``(signal_uid, time_index)`` on ``SignalWeightsStorage`` and
``(portfolio_identifier, time_index)`` on ``PortfolioWeightsStorage``, and every instance built
from them declares the same index; a provider adds it to its existing instances in a revision of
its own (ms-markets revision 0026 migrates only the Markets-owned tables). The indexes are not
unique and change no row.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-16 17:10:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SIGNAL_WEIGHTS_TABLE = "etfh_example__signalweightsts__main"
PORTFOLIO_WEIGHTS_TABLE = "etfh_example__portfolioweightsts__main"
SIGNAL_SERIES_INDEX = "ix__etfh_example__signalweightsts__main__signal_uid__time_index"
PORTFOLIO_SERIES_INDEX = "ix__etfh_example__portfolioweightsts__main__portfoli_ef8da4fe20"


def upgrade() -> None:
    op.create_index(SIGNAL_SERIES_INDEX, SIGNAL_WEIGHTS_TABLE, ["signal_uid", "time_index"])
    op.create_index(
        PORTFOLIO_SERIES_INDEX, PORTFOLIO_WEIGHTS_TABLE, ["portfolio_identifier", "time_index"]
    )


def downgrade() -> None:
    op.drop_index(PORTFOLIO_SERIES_INDEX, table_name=PORTFOLIO_WEIGHTS_TABLE)
    op.drop_index(SIGNAL_SERIES_INDEX, table_name=SIGNAL_WEIGHTS_TABLE)
