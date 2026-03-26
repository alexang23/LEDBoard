from auth import oauth2, schemas
from fastapi import APIRouter, Depends, Request, HTTPException, status
from database import get_db
from sqlalchemy.orm import Session # , load_only
from models.user import User, Permission, AccountType, AccountTypePermission
from auth import utils
from sqlalchemy import or_
# from global_log import glogger

router = APIRouter()

@router.get('/permission', response_model=schemas.ListPermissionResponse)
async def api_get_permission(request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()

    if login_user.acc_type == 'ALL' :
        glogger.warning('api_get_permission : You are not allowed to perform this action.', 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')
    
    permissions = db.query(Permission.code, Permission.name).all()
    glogger.info('api_get_permission : {}'.format(len(permissions)), {'user': '{},{}'.format(login_user.userid, login_user.name)})
    return {'status': 'success', 'results': len(permissions), 'permissions': permissions}

@router.get('/account_type', response_model=schemas.ListAccountTypeResponse)
async def api_get_account_type(request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()

    if login_user.acc_type == 'ALL' :
        glogger.warning('api_get_account_type : You are not allowed to perform this action.', 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')
    
    accounttypes = db.query(AccountType.acc_type, AccountType.name).all()
    glogger.info('api_get_account_type : {}'.format(len(accounttypes)), {'user': '{},{}'.format(login_user.userid, login_user.name)})
    return {'status': 'success', 'results': len(accounttypes), 'account_types': accounttypes}

@router.get('/account_type_permission', response_model=schemas.ListAccountTypePermissionResponse)
async def api_get_account_type_permission(acc_type: str, request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    
    if len(acc_type.strip()) == 0 :
        glogger.warning('api_get_account_type_permission : acc_type can not be null.'.format(), 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"acc_type can not be null.")
        
    accounttypepermissions = db.query(AccountTypePermission.code, AccountTypePermission.permission).filter(AccountTypePermission.acc_type == acc_type).all()

    if login_user.acc_type == 'ALL' :
        glogger.warning('api_get_account_type_permission : You are not allowed to perform this action.', 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')
        
    if not accounttypepermissions:
        glogger.warning('api_get_account_type_permission : No Permissions with this account type {} found.'.format(acc_type), 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"No Permissions with this account type: {acc_type} found")
    
    glogger.info('api_get_account_type_permission : {}'.format(len(accounttypepermissions)), {'user': '{},{}'.format(login_user.userid, login_user.name)})
    return {'status': 'success', 'results': len(accounttypepermissions), 'account_type_permissions': accounttypepermissions}

# @router.get('/account_type_permission/all', response_model=schemas.ListAllAccountTypePermissionResponse)
async def api_get_account_type_permission_all(request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    
    accounttypepermissions = db.query(AccountTypePermission.acc_type, AccountTypePermission.code, AccountTypePermission.permission).all()
    
    if login_user.acc_type == 'ALL' :
        glogger.warning('api_get_account_type_permission : You are not allowed to perform this action.', 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')
        
    if not accounttypepermissions:
        glogger.warning('api_get_account_type_permission : No Permissions with this account type {} found.'.format(), 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"No Permissions with this account type: found")
    
    glogger.info('api_get_account_type_permission : {}'.format(len(accounttypepermissions)), {'user': '{},{}'.format(login_user.userid, login_user.name)})
    return {'status': 'success', 'results': len(accounttypepermissions), 'account_type_permissions': accounttypepermissions}

@router.get('/me', response_model=schemas.UserResponse)
async def api_get_me(request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    user = db.query(User).filter(User.id == login_id).first()
    glogger.info('api_get_me : {},{}'.format(user.userid, user.name), {'user': '{},{}'.format(user.userid, user.name)})
    return user

@router.get('/', response_model=schemas.UserResponse)
async def api_get_user(userid: str, request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    user = db.query(User).filter(User.userid == userid).first()
    
    if login_user.userid != userid and login_user.acc_type != 'ADMIN':
        glogger.warning('api_get_user : {} You are not allowed to perform this action.'.format(userid), 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                    detail='You are not allowed to perform this action')
    if not user:
        glogger.warning('api_get_user : No user with this userid {} found.'.format(userid), 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"No user with this userid: {userid} found")
    glogger.info('api_get_user : {},{}'.format(user.userid, user.name), {'user': '{},{}'.format(login_user.userid, login_user.name)})
    return user

@router.get('/all', response_model=schemas.ListUserResponse)
async def api_get_all_user(request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()

    if login_user.acc_type == 'ALL' :
        glogger.warning('api_get_all_user : You are not allowed to perform this action.', 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')
    
    users = db.query(User).all()
    glogger.info('api_get_all_user : {}'.format(len(users)), {'user': '{},{}'.format(login_user.userid, login_user.name)})
    return {'status': 'success', 'results': len(users), 'users': users}

@router.get('/list', response_model=schemas.ListUserResponse)
#async def api_get_user_list(db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user), limit: int = 10, offset: int = 1, search: str = '', userid: str = '', name: str = '', active: bool = True, acc_type: str = ''):
async def api_get_user_list(request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user), limit: int = 10, offset: int = 1, search: str = '', userid: str = '', name: str = '', acc_type: str = ''):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    skip = (offset - 1) * limit
    
    if login_user.acc_type == 'ALL' :
        glogger.warning('api_get_user_list : You are not allowed to perform this action.', 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')
    
    #userlist = db.query(User).group_by(User.id).filter(User.title.contains(search)).limit(limit).offset(skip).all()
    userlist = db.query(User).filter( or_(User.userid.contains(search),User.name.contains(search) ,User.acc_type.contains(search)), 
                User.userid.contains(userid), User.name.contains(name), User.acc_type.contains(acc_type)).limit(limit).offset(skip).all()
    glogger.info('api_get_user_list : {}'.format(len(userlist)), {'user': '{},{}'.format(login_user.userid, login_user.name)})
    return {'status': 'success', 'results': len(userlist), 'users': userlist}
    
#@router.post('/test', response_model=schemas.ListUserResponse)
async def api_test_posts(request: Request, db: Session = Depends(get_db), limit: int = 10, page: int = 1, search: str = '', user_id: str = Depends(oauth2.require_user), acc_type: str = ''):
    glogger = request.app.state.glogger

    skip = (page - 1) * limit
    try:
        json = await request.json()
        print(json)
        # body = await request.body() ## will get seems like raw binary data ex: b'"{\\"event\\": \\"Alarm\\", \\"class\\": \\"ALARM\\", ..., \\"spec\\": \\"E84\\"}"'
        # print(body)
    except ValueError:
        #log_and_raise(HTTPStatus.BAD_REQUEST, reason="bad JSON body")
        print(ValueError)
        pass
    #users = db.query(User).group_by(User.id).filter(User.title.contains(search)).limit(limit).offset(skip).all()
    users = db.query(User).all()
    print('#### {},{}'.format(user_id, json['acc_type']))
    print('#### {},{},{}'.format(limit, page, acc_type))
    users = db.query(User).filter(User.acc_type == json['acc_type']).all()
    return {'status': 'success', 'results': len(users), 'users': users}

@router.post('/', status_code=status.HTTP_201_CREATED, response_model=schemas.UserResponse)
async def api_create_user(payload: schemas.CreateUserSchema, request: Request, db: Session = Depends(get_db)):
    glogger = request.app.state.glogger

    # Check if user already exist
    user = db.query(User).filter(User.userid == payload.userid).first()
    if user:
        glogger.warning('api_create_user : Userid {},{} already exist.'.format(user.userid, user.name), 
                        {'user': '{},{}'.format(user.userid, user.name)})
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail='Userid already exist')
    # Compare password and passwordConfirm
    if payload.password != payload.passwordConfirm:
        glogger.warning('api_create_user : Passwords do not match.', 
                        {'user': '{},{}'.format(user.userid, user.name)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='Passwords do not match')
    #  Hash the password
    payload.password = utils.hash_password(payload.password)
    del payload.passwordConfirm
    if payload.acc_type == None :
        payload.acc_type = 'OP'
    if payload.active == None :
        payload.active = True

    new_user = User(**payload.dict())
    
    try:    
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except Exception as e:
        db.rollback()
        glogger.error('api_create_user error : {}'.format(str(e)))
        return str(e), 400
    
    glogger.info('api_create_user : {},{}'.format(new_user.userid, new_user.name))
    return new_user

@router.delete('/')
async def api_delete_user(userid: str, request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    user_query = db.query(User).filter(User.userid == userid)
    user = user_query.first()
    
    if login_user.acc_type == 'OP':
        glogger.warning('api_delete_user : {} You are not allowed to perform this action.'.format(userid), 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')
    
    if not user:
        glogger.warning('api_delete_user : No user with this userid {} found.'.format(userid), 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f'No user with this userid: {userid} found')
        
    userid = user.userid
    name = user.name
        
    try:
        user_query.delete(synchronize_session=False)
        db.commit()
    except Exception as e:
        db.rollback()
        glogger.error('api_delete_user error : {}'.format(str(e)), 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        return str(e), 400
    
    
    glogger.info('api_delete_user : {},{}'.format(userid, name), {'user': '{},{}'.format(login_user.userid, login_user.name)})
    #return Response(status_code=status.HTTP_204_NO_CONTENT)
    return {'status': 'success delete'}

@router.put('/', response_model=schemas.UserResponse)
async def api_update_user(payload: schemas.UpdateUserSchema, request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    user_query = db.query(User).filter(User.userid == payload.userid)
    updated_user = user_query.first()
    
    login_user = db.query(User).filter(User.id == login_id).first()

    if not updated_user:
        glogger.warning('api_update_user : No user with this userid {} found.'.format(payload.userid), 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_200_OK,
                            detail=f'No User with this userid: {payload.userid} found')
    if str(updated_user.id) != login_id and login_user.acc_type != 'ADMIN' :
        glogger.warning('api_update_user : {},{} You are not allowed to perform this action.'.format(updated_user.userid, updated_user.name), 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')
           
    # print(payload.__getattribute__('name'))
    if 'password' in payload.dict().keys() :
        # print(payload.__getattribute__('password'))
        if len(payload.password) > 0 :
            payload.password = utils.hash_password(payload.password)
    
    try:
        user_query.update(payload.dict(exclude_unset=True), synchronize_session=False)
        db.commit()
    except Exception as e:
        db.rollback()
        glogger.error('api_update_user error : {}'.format(str(e)), 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        return str(e), 400
    
    glogger.info('api_update_user : {},{}'.format(updated_user.userid, updated_user.name), {'user': '{},{}'.format(login_user.userid, login_user.name)})
    return updated_user

# @router.get("/", response_model=List[schemas.User])
# def read_users(
#     db: Session = Depends(get_db),
#     skip: int = 0,
#     limit: int = 100,
#     current_user: User = Depends(deps.get_current_active_superuser),
# ) -> Any:
#     """
#     Retrieve users.
#     """
#     #users = crud.user.get_multi(db, skip=skip, limit=limit)
#     users = db.query.all().get_multi(db, skip=skip, limit=limit)
#     return users

# @users_api.route('', methods=['GET', 'PUT', 'POST', 'DELETE'])
# def users():
#     if request.method == 'GET':
#         users = User.query.all()
#         return jsonify(users)
#     else:
#         data = request.json
#         commonResponse = CommonAPIResponse('user', request.method)
#         returnData = None

#         user = User.query.filter_by(username=data.get('username')).first()

#         if request.method == 'POST':
#             if user is not None:
#                 return response(700)

#             user = User(
#                 name=data.get('name'),
#                 username=data.get('username'),
#                 acc_type=data.get('acc_type'),
#             )
#             user.set_password(data.get('password'))

#             db.session.add(user)
      
#             returnData = {
#                 'name': user.name,
#                 'username': user.username,
#                 'acc_type': user.acc_type,
#                 'last_updated': user.last_updated,
#             }
#         elif request.method == 'PUT':
#             if user is None:
#                 return response(701)
      
#             user.name = data.get('name', user.name)
#             user.acc_type = data.get('acc_type', user.acc_type)
#             if 'password' in data:
#                 user.set_password(data.get('password'))
            
#             returnData = {
#                 'name': user.name,
#                 'username': user.username,
#                 'acc_type': user.acc_type,
#                 'last_updated': user.last_updated,
#             }
#         elif request.method == 'DELETE':
#             if user is None:
#                 return response(701)
            
#             # db.session.delete(user)
#             User.query.filter_by(username=data.get('username')).delete()

#             returnData = data.get('username')
        
#         try:
#             db.session.commit()
#         except SQLAlchemyError as e:
#             error = 'Error {} {}'.format(commonResponse.getMessage('error'), str(e))
#             logger.error(error)
#             return response(500, error)
    
#         if request.method == 'PUT':
#             emit('user registered', {
#                 'name': user.name,
#                 'username': user.username,
#                 'acc_type': user.acc_type,
#                 'createdAt': str(user.createdAt)
#             }, json=True, broadcast=True, namespace='/ui_mgmt')
#         elif request.method == 'POST':
#             emit('user updated', {
#                 'name': user.name,
#                 'acc_type': user.acc_type,
#             }, json=True, broadcast=True, namespace='/ui_mgmt')
#         elif request.method == 'DELETE':
#             emit('user deleted', {
#                 'username': data.get('username')
#             }, json=True, broadcast=True, namespace='/ui_mgmt')

#         successMessage = 'Successfully {} {}'.format(
#             commonResponse.getMessage('success'),
#             request.json.get('username')
#         )
#         logger.info(successMessage)

#         return response(data=returnData, message=successMessage)

#################################################################################################################333

# @router.post('/', status_code=status.HTTP_201_CREATED, response_model=schemas.PostResponse)
# def create_post(post: schemas.CreatePostSchema, db: Session = Depends(get_db), owner_id: str = Depends(require_user)):
#     post.user_id = uuid.UUID(owner_id)
#     new_post = models.Post(**post.dict())
#     db.add(new_post)
#     db.commit()
#     db.refresh(new_post)
#     return new_post


# @router.put('/{id}', response_model=schemas.PostResponse)
# def update_post(id: str, post: schemas.UpdatePostSchema, db: Session = Depends(get_db), user_id: str = Depends(require_user)):
#     post_query = db.query(models.Post).filter(models.Post.id == id)
#     updated_post = post_query.first()

#     if not updated_post:
#         raise HTTPException(status_code=status.HTTP_200_OK,
#                             detail=f'No post with this id: {id} found')
#     if updated_post.user_id != uuid.UUID(user_id):
#         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
#                             detail='You are not allowed to perform this action')
#     post.user_id = user_id
#     post_query.update(post.dict(exclude_unset=True), synchronize_session=False)
#     db.commit()
#     return updated_post


# @router.get('/{id}', response_model=schemas.PostResponse)
# def get_post(id: str, db: Session = Depends(get_db), user_id: str = Depends(require_user)):
#     post = db.query(models.Post).filter(models.Post.id == id).first()
#     if not post:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
#                             detail=f"No post with this id: {id} found")
#     return post


# @router.delete('/{id}')
# def delete_post(id: str, db: Session = Depends(get_db), user_id: str = Depends(require_user)):
#     post_query = db.query(models.Post).filter(models.Post.id == id)
#     post = post_query.first()
#     if not post:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
#                             detail=f'No post with this id: {id} found')

#     if str(post.user_id) != user_id:
#         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
#                             detail='You are not allowed to perform this action')
#     post_query.delete(synchronize_session=False)
#     db.commit()
#     return Response(status_code=status.HTTP_204_NO_CONTENT)