from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class RedacaoRecord(Base):
    __tablename__ = 'redacoes'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tema = Column(String(255), nullable=False)
    texto_original = Column(Text, nullable=False)
    nota_total = Column(Float, nullable=False)
    c1 = Column(Integer, nullable=False) # Norma culta
    c2 = Column(Integer, nullable=False) # Tema e estrutura dissertativa
    c3 = Column(Integer, nullable=False) # Argumentação e repertório
    c4 = Column(Integer, nullable=False) # Coesão e conectivos
    c5 = Column(Integer, nullable=False) # Proposta de intervenção
    parecer = Column(Text, nullable=True)
    trechos_problemas = Column(Text, nullable=True)
    redacao_modelo = Column(Text, nullable=True)
    data_criacao = Column(DateTime, default=datetime.utcnow)

def init_db(db_path="sqlite:///data/redacoes.db"):
    engine = create_engine(db_path, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal
