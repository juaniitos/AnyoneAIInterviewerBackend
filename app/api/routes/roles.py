from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app import models, schemas

router = APIRouter(prefix="/roles", tags=["roles"])


@router.post("", response_model=schemas.RoleRead, status_code=status.HTTP_201_CREATED)
def create_role(payload: schemas.RoleCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Role).filter(models.Role.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Role already exists")
    role = models.Role(name=payload.name, description=payload.description)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


@router.get("", response_model=list[schemas.RoleRead])
def list_roles(db: Session = Depends(get_db)):
    return db.query(models.Role).order_by(models.Role.name).all()
