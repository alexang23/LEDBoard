from fastapi import APIRouter, Depends, HTTPException, status, Request
from database import get_db
from sqlalchemy.orm import Session
# from sqlalchemy import or_
# from global_log import glogger
from auth import oauth2
from models.user import User
# from global_log import glogger
from config import settings

router = APIRouter()

@router.get('/sw_version')
async def api_get_software_version(request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    
    if login_user.acc_type == 'ALL' :
        glogger.warning('api_get_message_list : You are not allowed to perform this action.', 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')
        
    return {'info': 'LEDBoard '+settings.SW_VERSION }