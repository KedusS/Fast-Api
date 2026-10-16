"""remove phone number from user

Revision ID: 1b3a7d9c2e40
Revises: aeff25f89db0
Create Date: 2026-10-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1b3a7d9c2e40"
down_revision: Union[str, None] = "aeff25f89db0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("users", "phone_number")


def downgrade() -> None:
    op.add_column("users", sa.Column("phone_number", sa.String(), nullable=True))
