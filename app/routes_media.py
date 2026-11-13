from fastapi import APIRouter, Depends

from .deps import current_user

router = APIRouter(dependencies=[Depends(current_user)])
