# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from datetime import datetime, timedelta
import MySQLdb
import json
from MySQLdb.constants.CLIENT import MULTI_STATEMENTS, MULTI_RESULTS
from django.http.response import HttpResponse, HttpResponseRedirect

from django.shortcuts import render, redirect, reverse
from django.core import serializers
#from django.contrib.auth.decorators import login_required
from extra.decorators import login_required

from mysql_platform.settings import INCEPTION_IP, INCEPTION_PORT, BACKUP_HOST_IP, BACKUP_HOST_PORT, BACKUP_PASSWORD
from mysql_platform.settings import BACKUP_USER
from statistics.models import MysqlInstance, MysqlInstanceGroup
from sql_review.models import SqlReviewRecord, SqlBackupRecord, SpecificationContentForSql, SpecificationTypeForSql
from sql_review.forms import SqlReviewRecordForm
from users.models import UserProfile, MessageRecord

from pure_pagination import Paginator, EmptyPage, PageNotAnInteger

from utils.log import my_logger


@login_required()
def review(request, record_id):
    record = SqlReviewRecord.objects.get(id=record_id)
    sql = record.sql
    instance = record.instance
    instance_ip = instance.ip
    instance_port = instance.port
    all_the_text = message_to_review_sql(option='--enable-check;--disable-remote-backup;', host=instance_ip,
                                         port=instance_port, sql=sql)
    try:
        conn = MySQLdb.connect(host=INCEPTION_IP, user='', passwd='', db='', port=INCEPTION_PORT,
                               client_flag=MULTI_STATEMENTS | MULTI_RESULTS)
        cur = conn.cursor()
        ret = cur.execute(all_the_text)
        num_fields = len(cur.description)
        field_names = [i[0] for i in cur.description]
        result = cur.fetchall()
        # 判断结果中是否有error level 为 2 的，如果有，则不做操作，如果没有则将sql_review_record 记录的 is_checked 设为1
        flag = 'success'
        for res in result:
            if res[2] == 2:
                flag = 'failed'
        if flag == 'success':
            record.is_checked = 1
            record.save()
        cur.close()
        conn.close()
        data = {
            'field_names': field_names,
            'result': result,
            'sub_module': '2_1',
            'flag': flag,
            'record_id': record.id,
            'sql': sql
        }
        return render(request, 'sql_review/result.html', data)
    except MySQLdb.Error as e:
        return HttpResponse('Mysql Error {}: {}'.format(e.args[0], e.args[1]), status=500)


@login_required(identity=('operation', 'project_manager'))
def pm_review(request, record_id):
    record = SqlReviewRecord.objects.get(id=record_id)
    sql = record.sql
    instance = record.instance
    instance_ip = instance.ip
    instance_port = instance.port
    all_the_text = message_to_review_sql(option='--enable-check;--disable-remote-backup;', host=instance_ip,
                                         port=instance_port, sql=sql)
    try:
        conn = MySQLdb.connect(host=INCEPTION_IP, user='', passwd='', db='', port=INCEPTION_PORT,
                               client_flag=MULTI_STATEMENTS | MULTI_RESULTS)
        cur = conn.cursor()
        ret = cur.execute(all_the_text)
        num_fields = len(cur.description)
        field_names = [i[0] for i in cur.description]
        result = cur.fetchall()
        cur.close()
        conn.close()
        data = {
            'field_names': field_names,
            'result': result,
            'sub_module': '2_1',
            'record_id': record.id,
            'sql': sql
        }
        return render(request, 'sql_review/pm_review_result.html', data)
    except MySQLdb.Error as e:
        return HttpResponse('Mysql Error {}: {}'.format(e.args[0], e.args[1]), status=500)


@login_required()
def submit_to_pm(request):
    record_id = request.POST.get('record_id', 0)
    record = SqlReviewRecord.objects.get(id=record_id)
    record.is_submitted = 1
    record.save()
    data = {
        'status': 'success'
    }
    return HttpResponse(json.dumps(data), content_type='application/json')


@login_required(identity=('operation', 'project_manager'))
def submit_to_ops(request, record_id):
    record = SqlReviewRecord.objects.get(id=record_id)
    record.is_reviewed = 1
    record.save()
    return redirect(reverse('sql_review_reviewed_list'))


@login_required(identity=('operation', 'project_manager'))
def reject_to_dev(request):
    # 拒绝执行sql，将审核状态置为2，写入通知消息到消息系统
    record = SqlReviewRecord.objects.get(id=request.POST.get('record_id'))
    if request.user.identity == 'project_manager':
        record.is_reviewed = 2
    else:
        record.is_executed = 2
    record.save()
    from_user = UserProfile.objects.get(id=request.user.id)
    to_user = UserProfile.objects.get(name=record.user_name)
    dev_message = MessageRecord()
    dev_message.info = '{} 拒绝了您的sql（{}）执行请求，具体原因为：{}'.format(request.user.name, record.for_what, request.POST.get('reject_reason'))
    dev_message.click_path = '/sql_review/submitted_list'
    dev_message.save()
    dev_message.send_from.add(from_user)
    dev_message.send_to.add(to_user)
    dev_message.save()
    if request.user.identity == 'operation':
        to_user = UserProfile.objects.get(name=record.pm_name)
        pm_message = MessageRecord()
        pm_message.info = '{} 拒绝了您的sql（{}）执行请求，具体原因为：{}'.format(request.user.name, record.for_what, request.POST.get('reject_reason'))
        pm_message.click_path = '/sql_review/submitted_list'
        pm_message.save()
        pm_message.send_from.add(from_user)
        pm_message.send_to.add(to_user)
        pm_message.save()
    data = {
        'status': 'success'
    }
    return HttpResponse(json.dumps(data), content_type='application/json')


def message_to_review_sql(host, port, sql, option):
    review_sql = """
    /*--user=inception;--password=inception;--host=""" + host + """;--port=""" + str(port) + """;""" + option + """*/
inception_magic_start;
""" + sql + """
inception_magic_commit;    
    """
    return review_sql


@login_required()
def step(request):
    instance_groups = MysqlInstanceGroup.objects.all()
    specification_type = SpecificationTypeForSql.objects.order_by('?')[0:3]
    content = []
    for idx, s_type in enumerate(specification_type):
        content.append(SpecificationContentForSql.objects.filter(type=s_type.id).order_by('?')[0:10])
    dict_content = {
        'content1': content[0],
        'content2': content[1],
        'content3': content[2]
    }
    # 查找出所有项目经理，以供开发选择
    project_manager = UserProfile.objects.filter(identity='project_manager')
    data = {
        'sub_module': '2_1',
        'instance_groups': instance_groups,
        'start_time': (datetime.now() + timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M'),
        'dict_content': dict_content,
        'project_manager': project_manager
    }
    return render(request, 'sql_review/step.html', data)


@login_required()
def submit_step(request):
    sql_review_form = SqlReviewRecordForm(request.POST)
    print(request.POST)
    if sql_review_form.is_valid():
        result = SqlReviewRecord()
        result.sql = sql_review_form.cleaned_data.get('sql')
        result.for_what = sql_review_form.cleaned_data.get('for_what')
        result.instance = sql_review_form.cleaned_data.get('instance')
        result.instance_group = sql_review_form.cleaned_data.get('instance_group')
        result.execute_time = sql_review_form.cleaned_data.get('execute_time')
        result.user_name = request.user.name
        result.pm_name = sql_review_form.cleaned_data.get('pm_name')
        result.save()
        data = {
            'result': 'success',
            'result_id': result.id
        }
        return HttpResponse(json.dumps(data), content_type='application/json')
    else:
        data = {
            'result': 'error'
        }
        return HttpResponse(json.dumps(data), content_type='application/json')


@login_required()
def instance_by_ajax_and_id(request):
    group_id = request.POST.get('group_id', '1')
    instance = MysqlInstance.objects.filter(group=group_id)
    return HttpResponse(serializers.serialize("json", instance), content_type='application/json')


@login_required()
def submitted_list(request):
    # 取出账号权限下所有的审核请求
    try:
        page = int(request.GET.get('page', 1))
        if page < 1:
            page = 1
    except ValueError:
        page = 1
    if request.user.identity == 'operation':
        record_list = SqlReviewRecord.objects.filter(is_checked=1,
                                                     is_submitted=1).order_by('-id')
    elif request.user.identity == 'project_manager':
        record_list = SqlReviewRecord.objects.filter(pm_name=request.user.name, is_checked=1,
                                                     is_submitted=1).order_by('-id')
    else:
        record_list = SqlReviewRecord.objects.filter(user_name=request.user.name, is_checked=1,
                                                     is_submitted=1).order_by('-id')

    p = Paginator(record_list, 10, request=request)
    try:
        record_list_in_pages = p.page(page)
    except EmptyPage:
        record_list_in_pages = p.page(1)
    data = {
        'record_list': record_list_in_pages,
        'sub_module': '2_2'
    }
    return render(request, 'sql_review/record_list.html', data)


@login_required()
def modify_submitted_sql(request):
    record = SqlReviewRecord.objects.get(id=request.POST.get('record_id'))
    new_sql = request.POST.get('sql', 'select 1')
    new_record = SqlReviewRecord()
    new_record.sql = new_sql
    new_record.user_name = request.user.username
    new_record.pm_name = record.pm_name
    new_record.for_what = record.for_what
    new_record.instance = record.instance
    new_record.instance_group = record.instance_group
    new_record.execute_time = record.execute_time
    new_record.save()
    data = {
        'new_id': new_record.id,
        'status': 'success'
    }
    return HttpResponse(json.dumps(data), content_type='application/json')


@login_required(identity=('operation', ))
def sql_review_before_execute(request, record_id):
    record = SqlReviewRecord.objects.get(id=record_id)
    sql = record.sql
    instance = record.instance
    instance_ip = instance.ip
    instance_port = instance.port
    # 组成一个inception 可以执行的 sql
    all_the_text = message_to_review_sql(option='--enable-check;--disable-remote-backup;',
                                         host=instance_ip, port=instance_port, sql=sql)
    try:
        conn = MySQLdb.connect(host=INCEPTION_IP, user='', passwd='', db='', port=INCEPTION_PORT,
                               client_flag=MULTI_STATEMENTS | MULTI_RESULTS)
        cur = conn.cursor()
        ret = cur.execute(all_the_text)
        field_names = [i[0] for i in cur.description]
        result = cur.fetchall()
        cur.close()
        conn.close()
        data = {
            'field_names': field_names,
            'result': result,
            'sub_module': '2_4',
            'record_id': record.id,
            'sql': sql
        }
        return render(request, 'sql_review/review_before_execute_result.html', data)
    except MySQLdb.Error as e:
        return HttpResponse('Mysql Error {}: {}'.format(e.args[0], e.args[1]), status=500)


@login_required(identity=('operation', ))
def sql_execute(request, record_id, ignore_flag):
    record = SqlReviewRecord.objects.get(id=record_id)
    sql = record.sql
    instance = record.instance
    instance_ip = instance.ip
    instance_port = instance.port
    # 组成一个inception 可以执行的 sql
    if ignore_flag == 'ignore':
        all_the_text = message_to_review_sql(option='--enable-execute;--enable-remote-backup;--enable-ignore-warnings;',
                                             host=instance_ip, port=instance_port, sql=sql)
    else:
        all_the_text = message_to_review_sql(option='--enable-execute;--enable-remote-backup;',
                                             host=instance_ip, port=instance_port, sql=sql)
    try:
        conn = MySQLdb.connect(host=INCEPTION_IP, user='', passwd='', db='', port=INCEPTION_PORT,
                               client_flag=MULTI_STATEMENTS | MULTI_RESULTS)
        cur = conn.cursor()
        ret = cur.execute(all_the_text)
        field_names = [i[0] for i in cur.description]
        result = cur.fetchall()
        # 判断结果中是否有执行成功的状态，如果有则将备份信息存入表中，等待给以后做回滚
        for res in result:
            if res[1] == 'EXECUTED' and (res[2] == 0 or res[2] == 1):
                sql_backup_instance = SqlBackupRecord()
                sql_backup_instance.review_record_id = record_id
                sql_backup_instance.backup_db_name = res[8]
                sql_backup_instance.sequence = res[7]
                sql_backup_instance.sql_sha1 = res[10]
                sql_backup_instance.save()
        # 判断结果中是否有error level 为 2 的，如果有，则不做操作，如果没有则将 sql_review_record 记录的 is_executed 设为1
        # 判断结果中是否有error level 为 1 的，如果有，并且忽略标记不为'ignore'，则不做操作，如果有，且忽略标记为'ignore'，则操作和上述一样
        flag = 'success'
        for res in result:
            if res[2] == 2 or (ignore_flag != 'ignore' and res[2] == 1):
                flag = 'failed'
        if flag == 'success':
            record.is_executed = 1
            record.save()
        cur.close()
        conn.close()
        data = {
            'field_names': field_names,
            'result': result,
            'sub_module': '2_4',
            'record_id': record.id,
            'sql': sql,
            'flag': flag
        }
        return render(request, 'sql_review/execute_result.html', data)
    except MySQLdb.Error as e:
        return HttpResponse('Mysql Error {}: {}'.format(e.args[0], e.args[1]), status=500)


def sql_execute_ignore_warning(request, record_id):

    return 's'


@login_required(identity=('operation', 'project_manager'))
def reviewed_list(request):
    # 取出账号权限下所有的项目经理审核完成列表
    try:
        page = int(request.GET.get('page', 1))
        if page < 1:
            page = 1
    except ValueError:
        page = 1

    if request.user.identity == 'operation':
        record_list = SqlReviewRecord.objects.filter(is_checked=1, is_reviewed=1).order_by('-id')
    elif request.user.identity == 'project_manager':
        record_list = SqlReviewRecord.objects.filter(pm_name=request.user.name, is_checked=1, is_reviewed=1).order_by('-id')
    else:
        record_list = SqlReviewRecord.objects.filter(is_checked=1, is_reviewed=1).order_by('-id')
    p = Paginator(record_list, 10, request=request)
    try:
        record_list_in_pages = p.page(page)
    except EmptyPage:
        record_list_in_pages = p.page(1)
    data = {
        'record_list': record_list_in_pages,
        'sub_module': '2_3',
    }
    return render(request, 'sql_review/reviewed_list.html', data)


@login_required(identity=('operation', ))
def finished_list(request):
    # 取出账号权限下所有的执行完成列表
    try:
        page = int(request.GET.get('page', 1))
        if page < 1:
            page = 1
    except ValueError:
        page = 1
    record_list = SqlReviewRecord.objects.filter(is_checked=1,is_reviewed=1,is_executed=1).order_by('-id')
    p = Paginator(record_list, 10, request=request)
    try:
        record_list_in_pages = p.page(page)
    except EmptyPage:
        record_list_in_pages = p.page(1)
    data = {
        'record_list': record_list_in_pages,
        'sub_module': '2_4',
    }
    return render(request, 'sql_review/finished_list.html', data)


@login_required(identity=('operation', ))
def rollback(request, record_id):
    rollback_list = SqlBackupRecord.objects.filter(review_record_id=record_id)
    for idx, obj in enumerate(rollback_list):
        backup_db = obj.backup_db_name
        sequence = obj.sequence
        sql = 'select * from $_$Inception_backup_information$_$ where `opid_time` = {}'.format(sequence)
        my_logger(level='info', message='执行SQL：' + sql, username=request.user.name, path=request.path)
        result = get_sql_result(BACKUP_HOST_IP, BACKUP_HOST_PORT, BACKUP_USER, BACKUP_PASSWORD, backup_db, sql)
        rollback_list[idx].sql = result[0][5]
        rollback_list[idx].db_host = result[0][6]
        rollback_list[idx].db_name = result[0][7]
        rollback_list[idx].db_table_name = result[0][8]
        rollback_sql = 'select  `rollback_statement` from {} where `opid_time` = {} limit 20'.format(result[0][8], sequence)
        my_logger(level='info', message='执行获取回滚SQL：' + rollback_sql, username=request.user.name, path=request.path)
        rollback_result = get_sql_result(BACKUP_HOST_IP, BACKUP_HOST_PORT, BACKUP_USER, BACKUP_PASSWORD, backup_db,
                                         rollback_sql)
        rollback_statement = str()
        for statement in rollback_result:
            rollback_statement += '{}\n'.format(statement[0])
        rollback_list[idx].rollback_statement = rollback_statement
    data = {
        'rollback_list': rollback_list,
        'sub_module': '2_4'
    }
    return render(request, 'sql_review/rollback.html', data)


def get_sql_result(host_ip, host_port, user, password, database, sql):
    try:
        conn = MySQLdb.connect(host=host_ip, user=user, passwd=password, db=database, port=host_port,
                               client_flag=MULTI_STATEMENTS | MULTI_RESULTS)
        cur = conn.cursor()
        ret = cur.execute(sql)
        result = cur.fetchall()
        cur.close()
        conn.close()
        return result
    except MySQLdb.Error as e:
        return 'error'


def dml_sql_in_transaction(host_ip, host_port, user, password, database, sql_list):
    conn = MySQLdb.connect(host=host_ip, user=user, passwd=password, db=database, port=host_port,
                           client_flag=MULTI_STATEMENTS | MULTI_RESULTS)
    cur = conn.cursor()
    try:
        for sql in sql_list:
            cur.execute(sql)
        cur.close()
        conn.commit()
        conn.close()
        return 'ok'
    except MySQLdb.Error as e:
        cur.close()
        conn.rollback()
        conn.close()
        return 'error'


@login_required(identity=('operation', ))
def ajax_rollback_by_sequence(request):
    sequence = request.POST.get('sequence')
    if sequence:
        sequence_list = sorted(sequence.strip(',').split(','), reverse=True)
    # 获取所有 sequence 的数据库名，进而获取回滚语句
        record = SqlBackupRecord.objects.get(sequence=sequence_list[0])
        backup_database_name = record.backup_db_name
        content = backup_database_name.split('_')
        host_ip = '{}.{}.{}.{}'.format(content[0], content[1], content[2], content[3])
        host_port = int(content[4])
        mysql_instance = MysqlInstance.objects.get(ip=host_ip, port=host_port)
        user = mysql_instance.login_instance_account
        password = mysql_instance.login_instance_password
        sql_list = list()
        for sequence in sequence_list:
            record = SqlBackupRecord.objects.get(sequence=sequence)
            backup_database_name = record.backup_db_name

            sql = 'select tablename from $_$Inception_backup_information$_$ where opid_time = {} limit 1'.format(sequence)
            result = get_sql_result(BACKUP_HOST_IP, BACKUP_HOST_PORT, BACKUP_USER, BACKUP_PASSWORD,
                                    backup_database_name, sql)
            table_name = result[0][0]
            sql = 'select rollback_statement from {} where opid_time = {}'.format(table_name, sequence)
            sql_result = get_sql_result(BACKUP_HOST_IP, BACKUP_HOST_PORT, BACKUP_USER, BACKUP_PASSWORD,
                                        backup_database_name, sql)
            if sql_result:
                for single_sql in sql_result:
                    sql_list.append(single_sql[0])
        if sql_list:
            result = dml_sql_in_transaction(host_ip, host_port, user, password, '', sql_list)
        else:
            result = 'empty'
        if result == 'ok':
            data = {
                'status': 'success',
                'message': '成功'
            }
        elif result == 'empty':
            data = {
                'status': 'empty',
                'message': '没有需要回滚的语句'
            }
        else:
            data = {
                'status': 'error',
                'message': '回滚语句执行失败'
            }
    else:
        data = {
            'status': 'empty',
            'message': '没有需要回滚的语句'
        }
    return HttpResponse(json.dumps(data), content_type='application/json')


@login_required(identity=('operation', ))
def osc_process(request, osc_id):
    sql = 'inception get osc_percent "{}"'.format(osc_id)
    try:
        conn = MySQLdb.connect(host=INCEPTION_IP, user='', passwd='', db='', port=INCEPTION_PORT,
                               client_flag=MULTI_STATEMENTS | MULTI_RESULTS)
        cur = conn.cursor()
        ret = cur.execute(sql)
        result = cur.fetchall()
        cur.close()
        conn.close()
        if result:
            result = tuple_to_dict(result[0], ('schema_name', 'table_name', 'sqlsha1', 'percent',
                                               'remain_time', 'info'))
            data = {
                'result': result,
                'osc_id': osc_id,
                'sub_module': '2_4'
            }
        else:
            result = {
                'schema_name': 'Empty',
                'table_name': 'Empty',
                'sqlsha1': osc_id,
                'percent': 'Empty',
                'remain_time': 'Empty',
                'info': 'Empty!!!',
            }
            data = {
                'result': result,
                'osc_id': osc_id,
                'sub_module': '2_4',
            }
        print(result)
        # return render(request, 'sql_review/review_before_execute_result.html', data)
        return render(request, 'sql_review/osc_process.html', data)
    except MySQLdb.Error as e:
        return HttpResponse('Mysql Error {}: {}'.format(e.args[0], e.args[1]), status=500)


def tuple_to_dict(tuple_arg, name):
    dict_arg = {}
    for index, arg in enumerate(name):
        dict_arg[arg] = tuple_arg[index]
    return dict_arg


@login_required(identity=('operation', ))
def ajax_osc_percent(request, osc_id):
    sql = 'inception get osc_percent "{}"'.format(osc_id)
    try:
        conn = MySQLdb.connect(host=INCEPTION_IP, user='', passwd='', db='', port=INCEPTION_PORT,
                               client_flag=MULTI_STATEMENTS | MULTI_RESULTS)
        cur = conn.cursor()
        ret = cur.execute(sql)
        result = cur.fetchall()
        cur.close()
        conn.close()
        if result:
            result = tuple_to_dict(result[0], ('schema_name', 'table_name', 'sqlsha1', 'percent',
                                               'remain_time', 'info'))
            result['info'] = result['info'].replace('\n', '<br ''/>')
            data = {
                'status': 'success',
                'process': result['percent'],
                'info': result
            }
        else:
            result = {
                'remain_time': '00:00',
                'info': 'Empty!!!'
            }
            data = {
                'status': 'empty',
                'process': 100,
                'info': result

            }
        return HttpResponse(json.dumps(data), content_type='application/json')
    except MySQLdb.Error as e:
        print(HttpResponse('Mysql Error {}: {}'.format(e.args[0], e.args[1]), status=500))
        return HttpResponse(json.dumps({'status': 'failed'}), content_type='application/json')


@login_required()
def more_specification(request):
    specification_type = SpecificationTypeForSql.objects.all()
    all_list = []
    for idx, types in enumerate(specification_type):
        tmp_dict = dict()
        tmp_dict['types'] = types
        tmp_dict['content'] = types.specificationcontentforsql_set.all()
        all_list.append(tmp_dict)
    data = {
        'all_list': all_list,
        'sub_module': '2_5'
    }
    return render(request, 'sql_review/specification.html', data)


def message_to_pm(request):
    # 给对应项目经理发邮件，以及站内信通知其审核sql
    record = SqlReviewRecord.objects.get(id=request.POST.get('record_id'))
    from_user = UserProfile.objects.get(id=request.user.id)
    to_user = UserProfile.objects.get(name=record.pm_name)
    message = MessageRecord()
    message.info = '{} 希望您能尽快审核该sql（{}）'.format(request.user.name, record.for_what)
    message.click_path = '/sql_review/submitted_list'
    message.save()
    message.send_from.add(from_user)
    message.send_to.add(to_user)
    message.save()
    return HttpResponse(json.dumps({'status': 'success'}), content_type='application/json')


def message_to_oper(request):
    # 发送给所有的运维
    record = SqlReviewRecord.objects.get(id=request.POST.get('record_id'))
    from_user = UserProfile.objects.get(id=request.user.id)
    to_users = UserProfile.objects.filter(identity='operation')
    for user in to_users:
        message = MessageRecord()
        message.info = '{} 希望您能尽快执行该sql（{}）'.format(request.user.name, record.for_what)
        message.click_path = '/sql_review/reviewed_list'
        message.save()
        message.send_from.add(from_user)
        message.send_to.add(user)
        message.save()
    return HttpResponse(json.dumps({'status': 'success'}), content_type='application/json')
