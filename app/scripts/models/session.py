import sqlalchemy as sa
from app.model.base import BaseModel


class Session(BaseModel):
    __tablename__ = 'session'

    id = sa.Column(sa.Integer(), primary_key=True, autoincrement=False)
    start_at_block = sa.Column(sa.Integer())
    end_at_block = sa.Column(sa.Integer())
    count_blocks = sa.Column(sa.Integer())
    era = sa.Column(sa.Integer())
    created_at_block = sa.Column(sa.Integer(), nullable=False)
    created_at_event = sa.Column(sa.Integer())
    count_validators = sa.Column(sa.Integer())
    count_nominators = sa.Column(sa.Integer())


class SessionValidator(BaseModel):
    __tablename__ = 'session_validator'

    session_id = sa.Column(sa.Integer(), primary_key=True, autoincrement=False)
    rank = sa.Column(sa.Integer(), primary_key=True, autoincrement=False, index=True)
    stash_key = sa.Column(sa.String(64), index=True)
    controller_key = sa.Column(sa.String(64), index=True, nullable=True)
    bonded_total = sa.Column(sa.Numeric(precision=65, scale=10), index=True)
    bonded_active = sa.Column(sa.Numeric(precision=65, scale=10), index=True)
    bonded_nominators = sa.Column(sa.Numeric(precision=65, scale=10), index=True)
    bonded_own = sa.Column(sa.Numeric(precision=65, scale=10),  nullable=True, index=True)
    count_nominators = sa.Column(sa.Integer(), nullable=True, index=True)
    commission = sa.Column(sa.Numeric(precision=65, scale=10), nullable=True, index=True)


class SessionNominator(BaseModel):
    __tablename__ = 'session_nominator'

    session_id = sa.Column(sa.Integer(), primary_key=True, autoincrement=False)
    rank_validator = sa.Column(sa.Integer(), primary_key=True, autoincrement=False, index=True)
    rank_nominator = sa.Column(sa.Integer(), primary_key=True, autoincrement=False, index=True)
    stash_key = sa.Column(sa.String(64), index=True)
    bonded = sa.Column(sa.Numeric(precision=65, scale=10), index=True)