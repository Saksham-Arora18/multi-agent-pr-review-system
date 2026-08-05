from sqlalchemy import Column, Integer, Text, Float, TIMESTAMP, ForeignKey, func
from sqlalchemy.orm import declarative_base, relationship
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class PullRequest(Base):
    __tablename__ = "pull_requests"

    id = Column(Integer, primary_key=True)
    repo = Column(Text, nullable=False)
    pr_number = Column(Integer, nullable=False)
    title = Column(Text)
    author = Column(Text)
    status = Column(Text, default="open")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    review_runs = relationship("ReviewRun", back_populates="pull_request", cascade="all, delete")
    chunks = relationship("PRChunk", back_populates="pull_request", cascade="all, delete")


class ReviewRun(Base):
    __tablename__ = "review_runs"

    id = Column(Integer, primary_key=True)
    pr_id = Column(Integer, ForeignKey("pull_requests.id", ondelete="CASCADE"))
    commit_sha = Column(Text)
    triggered_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    status = Column(Text, default="running")

    pull_request = relationship("PullRequest", back_populates="review_runs")
    comments = relationship("ReviewComment", back_populates="review_run", cascade="all, delete")


class PRChunk(Base):
    __tablename__ = "pr_chunks"

    id = Column(Integer, primary_key=True)
    pr_id = Column(Integer, ForeignKey("pull_requests.id", ondelete="CASCADE"))
    file_path = Column(Text, nullable=False)
    chunk_type = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(384))  # matches BAAI/bge-small-en-v1.5
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    pull_request = relationship("PullRequest", back_populates="chunks")


class ReviewComment(Base):
    __tablename__ = "review_comments"

    id = Column(Integer, primary_key=True)
    review_run_id = Column(Integer, ForeignKey("review_runs.id", ondelete="CASCADE"))
    agent_name = Column(Text, nullable=False)
    file_path = Column(Text)
    line_number = Column(Integer)
    comment = Column(Text, nullable=False)
    confidence_score = Column(Float)
    failure_type = Column(Text)
    status = Column(Text, default="pending")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    review_run = relationship("ReviewRun", back_populates="comments")