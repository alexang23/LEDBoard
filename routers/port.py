from auth import oauth2, schemas
from fastapi import APIRouter, Depends, HTTPException, status, Request
from database import get_db
from sqlalchemy.orm import Session
from models.user import User #, Permission, AccountType, AccountTypePermission
# from auth import utils
# from sqlalchemy import or_
from collections import OrderedDict
# from global_log import glogger
from config import Settings, settings
from dotenv import set_key
# from fastapi.encoders import jsonable_encoder

router = APIRouter()

@router.post('/enable')
async def api_port_enable(condition: schemas.PortInfo, request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    
    if login_user.acc_type == 'ALL' :
        glogger.warning('api_port_enable : You are not allowed to perform this action.', 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')

    result = 'OK'
    msg = '--'
    try:
        portno = condition.port_no
        tsc = request.app.state.tsc
        if portno not in tsc.loadport:
            result = 'Fail'
            msg = f'--'
            glogger.warning('api_port_enable : port_no = {portno}, result = {result}, msg = {msg}.', 
                            {'user': '{},{}'.format(login_user.userid, login_user.name)})
            return {'Result': result, 'PortNo': portno, 'Type': msg}

        if tsc.loadport[portno]['com'].upper() == 'E84':
            id = tsc.loadport[portno]['id']
            if condition.enable :
                tsc.e84[id].enable_port(True)
                tsc.loadport[portno]['enable'] = True
            else:
                tsc.e84[id].enable_port(False)
                tsc.loadport[portno]['enable'] = False
    
            print(f"api_port_enable : {portno}")
    
    except Exception as err:
        # print(str(err))
        glogger.warning(f'api_port_enable : port_no = {portno}, exception = {str(err)}', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f'port_no = {portno}, {str(err)}')
    
    # "Success": true/false,
    # "State": "OK"/”NG”,
    # "ErrorCode": 0,
    # "Message": "NA" / "PortID not found"
    glogger.info(f'api_port_enable : port_no = {portno}, result = {result}, type = {msg}.', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
    return {'Result': result, 'PortNo': portno, 'Type': msg}

@router.post('/fw-version')
async def api_port_fw_version(condition: schemas.PortInfo, request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    
    if login_user.acc_type == 'ALL' :
        glogger.warning('api_port_fw_version : You are not allowed to perform this action.', 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')

    result = 'OK'
    msg = '--'
    try:
        portno = condition.port_no
        tsc = request.app.state.tsc
        if portno not in tsc.loadport:
            result = 'Fail'
            msg = f'--'
            glogger.warning('api_port_fw_version : port_no = {portno}, result = {result}, msg = {msg}.', 
                            {'user': '{},{}'.format(login_user.userid, login_user.name)})
            return {'Result': result, 'PortNo': portno, 'Type': msg}

        type = tsc.loadport[portno]['com'].upper()
        if type == 'E84':
            id = tsc.loadport[portno]['id']
            tsc.e84[id].run_cmd('version')
            msg = f'E84'
            # print(f"api_port_fw_version : port_no = {portno} is E84") 
        else:
            msg = f'RFID'
            # print(f"api_port_fw_version : port_no = {portno} is RFID reader") 
    
    except Exception as err:
        # print(str(err))
        glogger.warning(f'api_port_fw_version : port_no = {portno}, exception = {str(err)}', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f'port_no = {portno}, {str(err)}')
    
    # "Success": true/false,
    # "State": "OK"/”NG”,
    # "ErrorCode": 0,
    # "Message": "NA" / "PortID not found"
    glogger.info(f'api_port_fw_version : port_no = {portno}, result = {result}, type = {msg}.', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
    return {'Result': result, 'PortNo': portno, 'Type': msg}

@router.get('/initial')
async def api_port_initial(request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    
    if login_user.acc_type == 'ALL' :
        glogger.warning('api_port_initial : You are not allowed to perform this action.', 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')

    result = 'OK'
    # msg = '--'
    loadports = []
    try:
        tsc = request.app.state.tsc
        for portno in tsc.loadport:
            port = OrderedDict()
            enable = tsc.loadport[portno]['enable']
            type = tsc.loadport[portno]['com'].upper()
            if type == 'E84':
                id = tsc.loadport[portno]['id']
                tsc.e84[id].run_cmd('version')
                # tsc.e84[id].run_cmd('mode')
                tsc.e84[id].run_cmd('status')
                # msg = f'E84'
                # print(f"api_port_initial : port_no = {portno} is E84")
            else:
                # msg = f'RFID'
                # print(f"api_port_initial : port_no = {portno} is RFID reader")
                pass
            port['port_no'] = portno
            port['enable'] = enable
            port['type'] = type
            loadports.append(port)
    
    except Exception as err:
        # print(str(err))
        glogger.warning(f'api_port_initial : exception = {str(err)}', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f'exception = {str(err)}')
    
    # "Success": true/false,
    # "State": "OK"/”NG”,
    # "ErrorCode": 0,
    # "Message": "NA" / "PortID not found"
    glogger.info(f'api_port_initial : result = {result}, loadports = {str(loadports)}.', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
    # return {'result': result, 'length': len(loadports), 'loadports': jsonable_encoder(loadports)}
    return {'result': result, 'length': len(loadports), 'loadports': loadports}

# @router.post('/connect', response_model=schemas.ConfigNetwork)
@router.post('/connect')
async def api_port_connect(condition: schemas.PortInfo, request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()

    if login_user.acc_type == 'ALL' :
        glogger.warning('api_port_connect : You are not allowed to perform this action.', 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')

    result = 'OK'
    msg = '--'
    try:
        portno = condition.port_no
        tsc = request.app.state.tsc
        if portno not in tsc.loadport:
            result = 'Fail'
            msg = f'--'
            glogger.warning('api_port_connect : port_no = {portno}, result = {result}, msg = {msg}.', 
                            {'user': '{},{}'.format(login_user.userid, login_user.name)})
            return {'Result': result, 'PortNo': portno, 'Type': msg}

        type = tsc.loadport[portno]['com'].upper()
        if type == 'E84':
            id = tsc.loadport[portno]['id']
            tsc.e84[id].run_cmd('version')
            # tsc.e84[id].run_cmd('mode')
            tsc.e84[id].run_cmd('status')
            msg = f'E84'
            # print(f"api_port_connect : port_no = {portno} is E84") 
        else:
            msg = f'RFID'
            # print(f"api_port_connect : port_no = {portno} is RFID reader") 
    
    except Exception as err:
        # print(str(err))
        glogger.warning(f'api_port_connect : port_no = {portno}, exception = {str(err)}', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f'port_no = {portno}, {str(err)}')
    
    # "Success": true/false,
    # "State": "OK"/”NG”,
    # "ErrorCode": 0,
    # "Message": "NA" / "PortID not found"
    glogger.info(f'api_port_connect : port_no = {portno}, result = {result}, type = {msg}.', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
    return {'Result': result, 'PortNo': portno, 'Type': msg}


# @router.post('/status', response_model=schemas.ConfigNetwork)
@router.post('/status')
async def api_port_status(condition: schemas.PortInfo, request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger
    glogger.warning('api_port_status : PortID={}'.format(condition.port_no))
    login_user = db.query(User).filter(User.id == login_id).first()
    
    if login_user.acc_type == 'ALL' :
        glogger.warning('api_port_status : port_no = {}. You do not have permission.'.format(condition.port_no), 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        # raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
        #                     detail='You are not allowed to perform this action')
        return {'Success': False,
                'State': 'NG',
                'ErrorCode': 403,
                'Message': 'You do not have permission.'}
    
    try:
        portno = condition.port_no
        tsc = request.app.state.tsc
        if portno not in tsc.loadport:
            glogger.warning('api_port_status : port_no {} is not exist.'.format(condition.port_no), 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
            # raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
            #                     detail=f'Do not support port_no = {portno}.')
            return {'Success': False,
                    'State': 'NG',
                    'ErrorCode': 500,
                    'Message': f'port_no {condition.port_no} is not exist.'}
        
        result = 0
        alarm_id= 0 
        alarm_text = ''
        carrier_id = 'NA'
        if tsc.loadport[portno]['com'] == 'e84':
            id = tsc.loadport[portno]['id']
            
            if tsc.loadport[portno]['dual'] == 1:
                status_msg = tsc.e84[id].port_status_msg2
                status = tsc.e84[id].port_status2
            else:
                status_msg = tsc.e84[id].port_status_msg
                status = tsc.e84[id].port_status
            print(f"id:{status}, {status_msg}")

            alarm_text = tsc.e84[id].alarm_text
            alarm_id = tsc.e84[id].alarm_id
            print(f"alarm id:{alarm_id}, {alarm_text}")

            result = status if alarm_id == 0 else 6

            if tsc.loadport[portno]['dual'] == 1:
                carrier_id = tsc.e84[id].rfid_data2
            else:
                carrier_id = tsc.e84[id].rfid_data
                
            if not carrier_id:
                carrier_id = ''
                
        elif tsc.loadport[portno]['com'] == 'rfid':
            id = tsc.loadport[portno]['id']
            if tsc.loadport[portno]['type'] == 'LF':
                carrier_id = tsc.rfid.rfids[id]
                if not carrier_id:
                    carrier_id = ''
    
    except Exception as err:
        print(str(err))
        glogger.warning(f'api_port_status : port_no = {portno}, {str(err)}', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
        # raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
        #                     detail=f'port_no = {portno}, {str(err)}')
        return {'Success': False,
                'State': 'NG',
                'ErrorCode': 500,
                'Message': str(err)}
    
    # users = db.query(User).all()
    # glogger.info('api_get_all_user : {}'.format(len(users)), {'user': '{},{}'.format(login_user.userid, login_user.name)})
    # "Success": true/false,
    # "State": "OK"/”NG”,
    # "ErrorCode": 0,
    # "Message": "NA" / "PortID not found",
    # "PortID": "Tool001-LP1",
    # "PortState": 3,
    # "CarrierID": "NA" / "123B12345"\
    # ---------------------------------------
#     'Result':NG/OK,
#     'PortID': 2,
#     'PortState': 4,
#     'ErrorCode': 0,
#     'Message': "",
#     'CarrierID': "NA"/"12345678"/""

    glogger.warning(f'api_port_status : PortID={portno}, PortState={result}, CarrierID={carrier_id}, ErrorCode={alarm_id}, Message={alarm_text}',
                    {'user': '{},{}'.format(login_user.userid, login_user.name)})

    # return {'Result': 'OK',
    return {'Success': True,
            'State': 'OK',
            'ErrorCode': alarm_id,
            'Message': alarm_text,
            'PortID': portno,
            'PortState': result,
            'CarrierID': carrier_id}

# @router.post('/reset', response_model=schemas.ConfigNetwork)
@router.post('/alarm-reset')
async def api_port_alarm_reset(condition: schemas.PortInfo, request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    
    if login_user.acc_type == 'ALL' :
        glogger.warning('api_port_alarm_reset : port_no = {}. You do not have permission.'.format(condition.port_no),
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        # raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
        #                     detail='You are not allowed to perform this action')
        return {'Success': False,
                'State': 'NG',
                'ErrorCode': 403,
                'Message': 'You do not have permission.'}
    
    result = 'OK'
    msg = 'Success'
    try:
        portno = condition.port_no
        tsc = request.app.state.tsc
        if portno not in tsc.loadport:
            glogger.warning('api_port_alarm_reset : port_no {} is not exist.'.format(condition.port_no), 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
            # raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
            #                     detail=f'Do not support port_no = {portno}.')
            return {'Success': False,
                    'State': 'NG',
                    'ErrorCode': 500,
                    'Message': f'port_no {condition.port_no} is not exist.'}
    
        if tsc.loadport[portno]['com'] == 'e84':
            id = tsc.loadport[portno]['id']
            tsc.e84[id].run_cmd('reset')
    
            print(f"api_port_alarm_reset : {portno}") 
        else:
            result = 'NG'
            msg = 'RFID reader do not support this command.'    
    
    except Exception as err:
        print(str(err))
        glogger.warning(f'api_port_alarm_reset : port_no = {portno}, {str(err)}', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
        # raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
        #                     detail=f'port_no = {portno}, {str(err)}')
        return {'Success': False,
                'State': 'NG',
                'ErrorCode': 500,
                'Message': str(err)}
    
    return {'Success': True,
            'State': result,
            'ErrorCode': 0,
            'Message': msg}
    # return {'Result': result,
    #         'Message': msg}

@router.post('/alarm-reset2')
async def api_port_alarm_reset2(condition: schemas.PortInfo, request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    
    if login_user.acc_type == 'ALL' :
        glogger.warning('api_port_alarm_reset2 : port_no = {}. You do not have permission.'.format(condition.port_no),
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        # raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
        #                     detail='You are not allowed to perform this action')
        return {'Success': False,
                'State': 'NG',
                'ErrorCode': 403,
                'Message': 'You do not have permission.'}
    
    result = 'OK'
    msg = 'Success'
    try:
        portno = condition.port_no
        tsc = request.app.state.tsc
        if portno not in tsc.loadport:
            glogger.warning('api_port_alarm_reset2 : port_no {} is not exist.'.format(condition.port_no), 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
            # raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
            #                     detail=f'Do not support port_no = {portno}.')
            return {'Success': False,
                    'State': 'NG',
                    'ErrorCode': 500,
                    'Message': f'port_no {condition.port_no} is not exist.'}
    
        if tsc.loadport[portno]['com'] == 'e84':
            id = tsc.loadport[portno]['id']
            tsc.e84[id].run_cmd('reset2')
    
            print(f"api_port_alarm_reset2 : {portno}") 
        else:
            result = 'NG'
            msg = 'RFID reader do not support this command.'    
    
    except Exception as err:
        print(str(err))
        glogger.warning(f'api_port_alarm_reset2 : port_no = {portno}, {str(err)}', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
        # raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
        #                     detail=f'port_no = {portno}, {str(err)}')
        return {'Success': False,
                'State': 'NG',
                'ErrorCode': 500,
                'Message': str(err)}
    
    return {'Success': True,
            'State': result,
            'ErrorCode': 0,
            'Message': msg}

# @router.post('/manual', response_model=schemas.ConfigNetwork)
@router.post('/manual-mode')
async def api_port_manual_mode(condition: schemas.PortInfo, request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    
    if login_user.acc_type == 'ALL' :
        glogger.warning('api_port_manual_mode : You are not allowed to perform this action.', 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')
    
    result = 'OK'
    msg = 'Success'
    try:
        portno = condition.port_no
        tsc = request.app.state.tsc
        if portno not in tsc.loadport:
            glogger.warning(f'api_port_manual_mode : Do not support port_no = {portno}.', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f'Do not support port_no = {portno}.')
    
        if tsc.loadport[portno]['com'] == 'e84':
            id = tsc.loadport[portno]['id']
            tsc.e84[id].run_cmd('manual')
    
            print(f"api_port_manual_mode : {portno}")
        else:
            result = 'NG'
            msg = 'RFID reader do not support this command.'  
    
    except Exception as err:
        print(str(err))
        glogger.warning(f'api_port_manual_mode : port_no = {portno}, {str(err)}', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f'port_no = {portno}, {str(err)}')

    # "Success": true/false,
    # "State": "OK"/”NG”,
    # "ErrorCode": 0,
    # "Message": "NA" / "PortID not found"
    return {'Result': result,
            'Message': msg}

@router.post('/manual-mode2')
async def api_port_manual_mode2(condition: schemas.PortInfo, request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    
    if login_user.acc_type == 'ALL' :
        glogger.warning('api_port_manual_mode2 : You are not allowed to perform this action.', 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')
    
    result = 'OK'
    msg = 'Success'
    try:
        portno = condition.port_no
        tsc = request.app.state.tsc
        if portno not in tsc.loadport:
            glogger.warning(f'api_port_manual_mode2 : Do not support port_no = {portno}.', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f'Do not support port_no = {portno}.')
    
        if tsc.loadport[portno]['com'] == 'e84':
            id = tsc.loadport[portno]['id']
            tsc.e84[id].run_cmd('manual2')
    
            print(f"api_port_manual_mode2 : {portno}")
        else:
            result = 'NG'
            msg = 'RFID reader do not support this command.'  
    
    except Exception as err:
        print(str(err))
        glogger.warning(f'api_port_manual_mode2 : port_no = {portno}, {str(err)}', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f'port_no = {portno}, {str(err)}')

    # "Success": true/false,
    # "State": "OK"/”NG”,
    # "ErrorCode": 0,
    # "Message": "NA" / "PortID not found"
    return {'Result': result,
            'Message': msg}

# @router.post('/auto', response_model=schemas.ConfigNetwork)
@router.post('/auto-mode')
async def api_port_auto_mode(condition: schemas.PortInfo, request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    
    if login_user.acc_type == 'ALL' :
        glogger.warning('api_port_auto_mode : You are not allowed to perform this action.', 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')
    
    result = 'OK'
    msg = 'Success'
    try:
        portno = condition.port_no
        tsc = request.app.state.tsc
        if portno not in tsc.loadport:
            glogger.warning(f'api_port_auto_mode : Do not support port_no = {portno}.', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f'Do not support port_no = {portno}.')
    
        if tsc.loadport[portno]['com'] == 'e84':
            id = tsc.loadport[portno]['id']
            tsc.e84[id].run_cmd('auto')
    
            print(f"api_port_auto_mode : {portno}")
        else:
            result = 'NG'
            msg = 'RFID reader do not support this command.'   
    
    except Exception as err:
        print(str(err))
        glogger.warning(f'api_port_auto_mode : port_no = {portno}, {str(err)}', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f'port_no = {portno}, {str(err)}')

    # "Result": "NG"/"OK",
    # "ErrorCode": 0,
    # "Message": "NA" / "PortID not found"
    return {'Result': result,
            'Message': msg}

@router.post('/auto-mode2')
async def api_port_auto_mode2(condition: schemas.PortInfo, request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    
    if login_user.acc_type == 'ALL' :
        glogger.warning('api_port_auto_mode2 : You are not allowed to perform this action.', 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')
    
    result = 'OK'
    msg = 'Success'
    try:
        portno = condition.port_no
        tsc = request.app.state.tsc
        if portno not in tsc.loadport:
            glogger.warning(f'api_port_auto_mode2 : Do not support port_no = {portno}.', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f'Do not support port_no = {portno}.')
    
        if tsc.loadport[portno]['com'] == 'e84':
            id = tsc.loadport[portno]['id']
            tsc.e84[id].run_cmd('auto2')
    
            print(f"api_port_auto_mode2 : {portno}")
        else:
            result = 'NG'
            msg = 'RFID reader do not support this command.'   
    
    except Exception as err:
        print(str(err))
        glogger.warning(f'api_port_auto_mode2 : port_no = {portno}, {str(err)}', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f'port_no = {portno}, {str(err)}')

    # "Result": "NG"/"OK",
    # "ErrorCode": 0,
    # "Message": "NA" / "PortID not found"
    return {'Result': result,
            'Message': msg}

# @router.post('/auto', response_model=schemas.ConfigNetwork)
@router.post('/check_light')
async def api_port_check_light(condition: schemas.PortInfo, request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    
    if login_user.acc_type == 'ALL' :
        glogger.warning('api_port_check_light : port_no = {}. You do not have permission.'.format(condition.port_no),
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        # raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
        #                     detail='You are not allowed to perform this action')
        return {'Success': False,
                'State': 'NG',
                'ErrorCode': 403,
                'Message': 'You do not have permission.'}

    result = 'OK'
    msg = 'Success'
    try:
        portno = condition.port_no
        tsc = request.app.state.tsc
        if portno not in tsc.loadport:
            glogger.warning('api_port_check_light : port_no {} is not exist.'.format(condition.port_no), 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
            # raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
            #                     detail=f'Do not support port_no = {portno}.')
            return {'Success': False,
                    'State': 'NG',
                    'ErrorCode': 500,
                    'Message': f'port_no {condition.port_no} is not exist.'}

        if tsc.loadport[portno]['com'] == 'e84':
            id = tsc.loadport[portno]['id']
            if condition.enable :
                tsc.e84[id].run_cmd('check_light_on')
            else:
                tsc.e84[id].run_cmd('check_light_off')
    
            print(f"api_port_check_light : {portno}")
        else:
            result = 'NG'
            msg = 'RFID reader do not support this command.'   
    
    except Exception as err:
        print(str(err))
        glogger.warning(f'api_port_check_light : port_no = {portno}, {str(err)}', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
        # raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
        #                     detail=f'port_no = {portno}, {str(err)}')
        return {'Success': False,
                'State': 'NG',
                'ErrorCode': 500,
                'Message': str(err)}

    return {'Success': True,
            'State': result,
            'ErrorCode': 0,
            'Message': msg}
    # return {'Result': result,
    #         'Message': msg}

# @router.post('/last_error', response_model=schemas.ConfigNetwork)
@router.post('/last_error')
async def api_port_last_error(condition: schemas.PortInfo, request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    
    if login_user.acc_type == 'ALL' :
        glogger.warning('api_port_last_error : You are not allowed to perform this action.', 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')
    
    result = 'OK'
    msg = 'Success'
    alarm_id = 0
    alarm_text = ''
    try:
        portno = condition.port_no
        tsc = request.app.state.tsc
        if portno not in tsc.loadport:
            glogger.warning(f'api_port_last_error : Do not support port_no = {portno}.', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f'Do not support port_no = {portno}.')
    
        if tsc.loadport[portno]['com'] == 'e84':
            id = tsc.loadport[portno]['id']
            tsc.e84[id].run_cmd('last_error')

            alarm_text = tsc.e84[id].alarm_text
            alarm_id = tsc.e84[id].alarm_id
            print(f"alarm id:{alarm_id}, {alarm_text}")
    
            print(f"api_port_last_error : {portno}")
        else:
            result = 'NG'
            msg = 'RFID reader do not support this command.'   
    
    except Exception as err:
        print(str(err))
        glogger.warning(f'api_port_last_error : port_no = {portno}, {str(err)}', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f'port_no = {portno}, {str(err)}')

    # "Result": "NG"/"OK",
    # "ErrorCode": 0,
    # "Message": "NA" / "PortID not found"
    return {'Result': result,
            'Message': msg,
            'ErrorCode': alarm_id,
            'ErrorMessage': alarm_text}
    
@router.post('/alarm')
async def api_port_alarm(condition: schemas.AlarmInfo, request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    
    if login_user.acc_type == 'ALL' :
        glogger.warning('api_port_alarm : You are not allowed to perform this action.', 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')
    
    result = 'OK'
    msg = 'Success'
    alarm_id = 0
    alarm_text = ''
    try:
        portno = condition.port_no
        alarm_id = condition.alarm_id
        tsc = request.app.state.tsc
        if portno not in tsc.loadport:
            glogger.warning(f'api_port_alarm : Do not support port_no = {portno}.', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f'Do not support port_no = {portno}.')
    
        if tsc.loadport[portno]['com'] == 'e84':
            id = tsc.loadport[portno]['id']
            tsc.e84[id].run_cmd(f"alarm {alarm_id}")

            # alarm_text = tsc.e84[id].alarm_text
            # alarm_id = tsc.e84[id].alarm_id
            # print(f"alarm id:{alarm_id}, {alarm_text}")
    
            print(f"api_port_alarm : portno = {portno}, alarm_id = {alarm_id}")
        else:
            result = 'NG'
            msg = 'E84 do not support this command.'   
    
    except Exception as err:
        print(str(err))
        glogger.warning(f'api_port_alarm : port_no = {portno}, alarm_id = {alarm_id}, {str(err)}', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f'port_no = {portno}, alarm_id = {alarm_id}, {str(err)}')

    # "Result": "NG"/"OK",
    # "ErrorCode": 0,
    # "Message": "NA" / "PortID not found"
    return {'Result': result,
            'Message': msg,
            'ErrorCode': alarm_id,
            'ErrorMessage': alarm_text}

# @router.post('/ps', response_model=schemas.ConfigNetwork)
@router.post('/ps')
async def api_port_ps(condition: schemas.PortInfo, request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    
    if login_user.acc_type == 'ALL' :
        glogger.warning('api_port_ps : You are not allowed to perform this action.', 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')
    
    result = 'OK'
    msg = 'Success'
    try:
        portno = condition.port_no
        tsc = request.app.state.tsc
        if portno not in tsc.loadport:
            glogger.warning(f'api_port_ps : Do not support port_no = {portno}.', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f'Do not support port_no = {portno}.')

        if tsc.loadport[portno]['com'] == 'e84':
            id = tsc.loadport[portno]['id']
            if condition.enable :
                tsc.e84[id].run_cmd('ps_on')
            else:
                tsc.e84[id].run_cmd('ps_off')
    
            print(f"api_port_ps : {portno}")
        else:
            result = 'NG'
            msg = 'RFID reader do not support this command.'   
    
    except Exception as err:
        print(str(err))
        glogger.warning(f'api_port_ps : port_no = {portno}, {str(err)}', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f'port_no = {portno}, {str(err)}')

    # "Result": "NG"/"OK",
    # "ErrorCode": 0,
    # "Message": "NA" / "PortID not found"
    return {'Result': result,
            'Message': msg}

# @router.post('/clamp', response_model=schemas.ConfigNetwork)
@router.post('/clamp')
async def api_port_clamp(condition: schemas.PortInfo, request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    
    if login_user.acc_type == 'ALL' :
        glogger.warning('api_port_clamp : You are not allowed to perform this action.', 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')
    
    result = 'OK'
    msg = 'Success'
    try:
        portno = condition.port_no
        tsc = request.app.state.tsc
        if portno not in tsc.loadport:
            glogger.warning(f'api_port_clamp : Do not support port_no = {portno}.', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f'Do not support port_no = {portno}.')

        if tsc.loadport[portno]['com'] == 'e84':
            id = tsc.loadport[portno]['id']
            if condition.enable :
                tsc.e84[id].run_cmd('clamp_on')
            else:
                tsc.e84[id].run_cmd('clamp_off')
    
            print(f"api_port_clamp : {portno}")
        else:
            result = 'NG'
            msg = 'RFID reader do not support this command.'   
    
    except Exception as err:
        print(str(err))
        glogger.warning(f'api_port_clamp : port_no = {portno}, {str(err)}', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f'port_no = {portno}, {str(err)}')

    # "Result": "NG"/"OK",
    # "ErrorCode": 0,
    # "Message": "NA" / "PortID not found"
    return {'Result': result,
            'Message': msg}

# @router.post('/light', response_model=schemas.ConfigNetwork)
@router.post('/light')
async def api_port_light(condition: schemas.PortInfo, request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    
    if login_user.acc_type == 'ALL' :
        glogger.warning('api_port_light : You are not allowed to perform this action.', 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')
    
    result = 'OK'
    msg = 'Success'
    try:
        portno = condition.port_no
        tsc = request.app.state.tsc
        if portno not in tsc.loadport:
            glogger.warning(f'api_port_light : Do not support port_no = {portno}.', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f'Do not support port_no = {portno}.')

        if tsc.loadport[portno]['com'] == 'e84':
            id = tsc.loadport[portno]['id']
            if condition.enable :
                tsc.e84[id].run_cmd('light_on')
            else:
                tsc.e84[id].run_cmd('light_off')
    
            print(f"api_port_light : {portno}")
        else:
            result = 'NG'
            msg = 'RFID reader do not support this command.'   
    
    except Exception as err:
        print(str(err))
        glogger.warning(f'api_port_light : port_no = {portno}, {str(err)}', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f'port_no = {portno}, {str(err)}')

    # "Result": "NG"/"OK",
    # "ErrorCode": 0,
    # "Message": "NA" / "PortID not found"
    return {'Result': result,
            'Message': msg}

# @router.post('/eqer', response_model=schemas.ConfigNetwork)
@router.post('/eqer')
async def api_port_eqer(condition: schemas.PortInfo, request: Request, db: Session = Depends(get_db), login_id: str = Depends(oauth2.require_user)):
    glogger = request.app.state.glogger

    login_user = db.query(User).filter(User.id == login_id).first()
    
    if login_user.acc_type == 'ALL' :
        glogger.warning('api_port_eqer : You are not allowed to perform this action.', 
                        {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='You are not allowed to perform this action')
    
    result = 'OK'
    msg = 'Success'
    try:
        portno = condition.port_no
        tsc = request.app.state.tsc
        if portno not in tsc.loadport:
            glogger.warning(f'api_port_eqer : Do not support port_no = {portno}.', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f'Do not support port_no = {portno}.')

        if tsc.loadport[portno]['com'] == 'e84':
            id = tsc.loadport[portno]['id']
            if condition.enable :
                tsc.e84[id].run_cmd('eqer_on')
            else:
                tsc.e84[id].run_cmd('eqer_off')
    
            print(f"api_port_eqer : {portno}")
        else:
            result = 'NG'
            msg = 'RFID reader do not support this command.'   
    
    except Exception as err:
        print(str(err))
        glogger.warning(f'api_port_eqer : port_no = {portno}, {str(err)}', 
                {'user': '{},{}'.format(login_user.userid, login_user.name)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f'port_no = {portno}, {str(err)}')

    # "Result": "NG"/"OK",
    # "ErrorCode": 0,
    # "Message": "NA" / "PortID not found"
    return {'Result': result,
            'Message': msg}