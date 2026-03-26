from datetime import timedelta
from auth import schemas
from fastapi import APIRouter, Request, Response, status, Depends, HTTPException
# from pydantic import EmailStr

from auth import oauth2
from models.user import User
from auth import utils
from sqlalchemy.orm import Session
from database import get_db
from auth.oauth2 import AuthJWT
from config import settings
# from global_log import glogger


router = APIRouter()
ACCESS_TOKEN_EXPIRES_IN = settings.ACCESS_TOKEN_EXPIRES_IN
REFRESH_TOKEN_EXPIRES_IN = settings.REFRESH_TOKEN_EXPIRES_IN

## move to app\routers\user.py
# @router.post('/register', status_code=status.HTTP_201_CREATED, response_model=schemas.UserResponse)
# async def create_user(payload: schemas.CreateUserSchema, db: Session = Depends(get_db)):
#     # Check if user already exist
#     user = db.query(User).filter(
#         User.userid == payload.userid.lower()).first()
#     if user:
#         raise HTTPException(status_code=status.HTTP_409_CONFLICT,
#                             detail='Userid already exist')
#     # Compare password and passwordConfirm
#     if payload.password != payload.passwordConfirm:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST, detail='Passwords do not match')
#     #  Hash the password
#     payload.password = utils.hash_password(payload.password)
#     del payload.passwordConfirm
#     if payload.acc_type == None :
#         payload.acc_type = 'OP'
#     if payload.active == None :
#         payload.active = True
#     #payload.verified = True
#     #payload.email = EmailStr(payload.email.lower())
#     new_user = User(**payload.dict())
#     db.add(new_user)
#     db.commit()
#     db.refresh(new_user)
#     return new_user


@router.post('/login')
def api_login(payload: schemas.LoginUserSchema, request: Request, response: Response, db: Session = Depends(get_db), Authorize: AuthJWT = Depends()):
    glogger = request.app.state.glogger

    # Check if the user exist
    user = db.query(User).filter(User.userid == payload.userid).first()
    if not user:
        glogger.warning('api_login : {} Incorrect userid.'.format(payload.userid))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='Incorrect Userid')

    # Check if the password is valid
    if not utils.verify_password(payload.password, user.password):
        glogger.warning('api_login : {} Incorrect Password.'.format(payload.userid))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='Incorrect Userid or Password')

    # Create access token
    access_token = Authorize.create_access_token(
        subject=str(user.id), expires_time=timedelta(minutes=ACCESS_TOKEN_EXPIRES_IN))

    # Create refresh token
    refresh_token = Authorize.create_refresh_token(
        subject=str(user.id), expires_time=timedelta(minutes=REFRESH_TOKEN_EXPIRES_IN))

    # Store refresh and access tokens in cookie
    response.set_cookie('access_token', access_token, ACCESS_TOKEN_EXPIRES_IN * 60,
                        ACCESS_TOKEN_EXPIRES_IN * 60, '/', None, False, True, 'lax')
    response.set_cookie('refresh_token', refresh_token, REFRESH_TOKEN_EXPIRES_IN * 60,
                        REFRESH_TOKEN_EXPIRES_IN * 60, '/', None, False, True, 'lax')
    response.set_cookie('logged_in', 'True', ACCESS_TOKEN_EXPIRES_IN * 60,
                        ACCESS_TOKEN_EXPIRES_IN * 60, '/', None, False, False, 'lax')

    glogger.info('api_login : {},{} Success.'.format(user.userid, user.name), 
                        {'user': '{},{}'.format(user.userid, user.name)})
    # Send both access
    return {'status': 'success', 'userid': user.userid, 'name': user.name, 'acc_type': user.acc_type, 'access_token': access_token}


@router.post('/refresh')
def api_refresh_token(request: Request, response: Response, Authorize: AuthJWT = Depends(), db: Session = Depends(get_db)):
    try:
        glogger = request.app.state.glogger

        print(Authorize._refresh_cookie_key)
        Authorize.jwt_refresh_token_required()

        user_id = Authorize.get_jwt_subject()
        if not user_id:
            glogger.warning('api_refresh_token : Could not refresh access token.')
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail='Could not refresh access token')
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            glogger.warning('api_refresh_token : {} The user belonging to this token no logger exist.'.format(user_id))
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail='The user belonging to this token no logger exist')
        access_token = Authorize.create_access_token(
            subject=str(user.id), expires_time=timedelta(minutes=ACCESS_TOKEN_EXPIRES_IN))
    except Exception as e:
        error = e.__class__.__name__
        if error == 'MissingTokenError':
            glogger.error('api_refresh_token : status code={}, detail=Please provide refresh token.'.format(status.HTTP_400_BAD_REQUEST))
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Please provide refresh token')
        glogger.error('api_refresh_token : status code={}, detail={}.'.format(status.HTTP_400_BAD_REQUEST, error))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    response.set_cookie('access_token', access_token, ACCESS_TOKEN_EXPIRES_IN * 60,
                        ACCESS_TOKEN_EXPIRES_IN * 60, '/', None, False, True, 'lax')
    response.set_cookie('logged_in', 'True', ACCESS_TOKEN_EXPIRES_IN * 60,
                        ACCESS_TOKEN_EXPIRES_IN * 60, '/', None, False, False, 'lax')
    
    glogger.info('api_refresh_token : {},{} Success.'.format(user.userid, user.name), {'user': '{},{}'.format(user.userid, user.name)})
    return {'access_token': access_token}


@router.get('/logout', status_code=status.HTTP_200_OK)
def api_logout(request: Request, response: Response, Authorize: AuthJWT = Depends(), db: Session = Depends(get_db), user_id: str = Depends(oauth2.require_user)):
    try:
        glogger = request.app.state.glogger

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            glogger.warning('api_logout : {} The user does not exist.'.format(user_id))
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail='The user does not exist')
        name = user.name
        Authorize.unset_jwt_cookies()
        response.set_cookie('logged_in', '', -1)
    except Exception as e:
        error = e.__class__.__name__
        glogger.error('api_logout : status code={}, detail={}.'.format(status.HTTP_400_BAD_REQUEST, error), {'user': '{}'.format(user_id)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    glogger.info('api_logout : {},{} Success.'.format(user_id, name), {'user': '{},{}'.format(user_id, name)})
    return {'status': 'success'}

