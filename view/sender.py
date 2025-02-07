''' Sneder '''
import csv
import io
import random

import arrow
from flask import Blueprint, g, jsonify, redirect, render_template, request

from celery_task.task_sendermailer import sender_mailer_start
from module.sender import SenderCampaign, SenderLogs, SenderReceiver
from module.team import Team
from module.users import User
from view.utils import check_the_team_and_project_are_existed

VIEW_SENDER = Blueprint('sender', __name__, url_prefix='/sender')


@VIEW_SENDER.route('/<pid>/<tid>/', methods=('GET', 'POST'))
def index(pid, tid):
    ''' Index page '''
    team, project, _redirect = check_the_team_and_project_are_existed(
        pid=pid, tid=tid)
    if _redirect:
        return _redirect

    is_admin = (g.user['account']['_id'] in team['chiefs'] or
                g.user['account']['_id'] in team['owners'] or
                g.user['account']['_id'] in project['owners'])

    if not is_admin:
        return redirect('/')

    # ..note::
    # 1. create campaign (campaign name) / list campaign
    # 2. write title, content(jinja2, markdown)
    # 3. pick up receiver
    # 4. send / send test

    if request.method == 'GET':
        return render_template('./sender.html')

    if request.method == 'POST':
        data = request.get_json()

        if 'casename' in data and data['casename'] == 'get':
            campaigns = list(SenderCampaign.get_list(
                pid=team['pid'], tid=team['tid']))
            raw_users_info = User.get_info(
                uids=[c['created']['uid'] for c in campaigns])
            users_info = {}
            for uid, value in raw_users_info.items():
                users_info[uid] = {
                    'uid': uid, 'name': value['profile']['badge_name']}

            return jsonify({'campaigns': campaigns, 'users_info': users_info})

        if 'casename' in data and data['casename'] == 'create':
            resp = SenderCampaign.create(
                name=data['name'], pid=team['pid'], tid=team['tid'], uid=g.user['account']['_id'])

            return jsonify({'cid': resp['_id']})

    return jsonify({})


@VIEW_SENDER.route('/<pid>/<tid>/campaign/<cid>/', methods=('GET', 'POST'))
def campaign(pid, tid, cid):
    ''' campaign '''
    team, project, _redirect = check_the_team_and_project_are_existed(
        pid=pid, tid=tid)
    if _redirect:
        return _redirect

    is_admin = (g.user['account']['_id'] in team['chiefs'] or
                g.user['account']['_id'] in team['owners'] or
                g.user['account']['_id'] in project['owners'])

    if not is_admin:
        return redirect('/')

    campaign_data = SenderCampaign.get(cid=cid, pid=pid, tid=tid)

    return render_template('./sender_campaign_index.html', campaign=campaign_data, team=team)


@VIEW_SENDER.route('/<pid>/<tid>/campaign/<cid>/content', methods=('GET', 'POST'))
def campaign_content(pid, tid, cid):
    ''' Campaign content '''
    team, project, _redirect = check_the_team_and_project_are_existed(
        pid=pid, tid=tid)
    if _redirect:
        return _redirect

    is_admin = (g.user['account']['_id'] in team['chiefs'] or
                g.user['account']['_id'] in team['owners'] or
                g.user['account']['_id'] in project['owners'])

    if not is_admin:
        return redirect('/')

    if request.method == 'GET':
        campaign_data = SenderCampaign.get(
            cid=cid, pid=team['pid'], tid=team['tid'])

        return render_template('./sender_campaign_content.html', campaign=campaign_data, team=team)

    if request.method == 'POST':
        data = request.get_json()

        if 'casename' in data and data['casename'] == 'get':
            campaign_data = SenderCampaign.get(
                cid=cid, pid=team['pid'], tid=team['tid'])
            return jsonify({'mail': campaign_data['mail']})

        if 'casename' in data and data['casename'] == 'save':
            resp = SenderCampaign.save_mail(
                cid=cid,
                subject=data['data']['subject'].strip(),
                content=data['data']['content'].strip(),
                preheader=data['data']['preheader'].strip(),
                layout=data['data']['layout'].strip(),
            )
            return jsonify({'mail': resp['mail']})

    return jsonify({}), 404


@VIEW_SENDER.route('/<pid>/<tid>/campaign/<cid>/receiver', methods=('GET', 'POST'))
def campaign_receiver(pid, tid, cid):
    ''' campaign receiver '''
    # pylint: disable=too-many-branches,too-many-locals,too-many-return-statements
    team, project, _redirect = check_the_team_and_project_are_existed(
        pid=pid, tid=tid)
    if _redirect:
        return _redirect

    is_admin = (g.user['account']['_id'] in team['chiefs'] or
                g.user['account']['_id'] in team['owners'] or
                g.user['account']['_id'] in project['owners'])

    if not is_admin:
        return redirect('/')

    campaign_data = SenderCampaign.get(
        cid=cid, pid=team['pid'], tid=team['tid'])
    if request.method == 'GET':
        return render_template('./sender_campaign_receiver.html', campaign=campaign_data, team=team)

    if request.method == 'POST':
        data = {}

        if request.is_json:
            data = request.get_json()

        if data and 'casename' in data and data['casename'] == 'getinit':
            teams = []
            for _team in Team.list_by_pid(pid=team['pid']):
                teams.append({'tid': _team['tid'], 'name': _team['name']})

            team_w_tags = []
            if 'tag_members' in team:
                team_w_tags = team['tag_members']

            sender_receiver = SenderReceiver.get(pid=team['pid'], cid=cid)

            picktags = []
            if 'team_w_tags' in campaign_data['receiver'] and \
                    team['tid'] in campaign_data['receiver']['team_w_tags']:
                picktags = campaign_data['receiver']['team_w_tags'][team['tid']]

            return jsonify({'teams': teams,
                            'team_w_tags': team_w_tags,
                            'pickteams': campaign_data['receiver']['teams'],
                            'picktags': picktags,
                            'is_all_users': campaign_data['receiver']['all_users'],
                            'all_users_count': User.count(),
                            'filedata': sender_receiver,
                            })

        if data and 'casename' in data and data['casename'] == 'save':
            tids = [team['tid'] for team in Team.list_by_pid(pid=team['pid'])]

            _result = []
            for tid_info in tids:
                if tid_info in data['pickteams']:
                    _result.append(tid_info)

            _team_w_tags = []
            if 'tag_members' in team:
                for tag in team['tag_members']:
                    if tag['id'] in data['picktags']:
                        _team_w_tags.append(tag['id'])

            return jsonify(SenderCampaign.save_receiver(
                cid=cid, teams=_result, team_w_tags={
                    team['tid']: _team_w_tags},
                all_users=bool(data['is_all_users']))['receiver'])

        if request.form['uploadtype'] == 'remove':
            SenderReceiver.remove(pid=team['pid'], cid=cid)

            return jsonify({'file': [],
                            'uploadtype': request.form['uploadtype'],
                            })

        if request.files and 'file' in request.files:
            csv_file = list(csv.DictReader(io.StringIO(
                request.files['file'].read().decode('utf8'))))
            if request.form['uploadtype'] == 'replace':
                SenderReceiver.replace(
                    pid=team['pid'], cid=cid, datas=csv_file)
            elif request.form['uploadtype'] == 'update':
                SenderReceiver.update(pid=team['pid'], cid=cid, datas=csv_file)

            return jsonify({'file': csv_file,
                            'uploadtype': request.form['uploadtype'],
                            })

    return jsonify({}), 404


@VIEW_SENDER.route('/<pid>/<tid>/campaign/<cid>/schedule', methods=('GET', 'POST'))
def campaign_schedule(pid, tid, cid):
    ''' campaign schedule '''
    # pylint: disable=too-many-locals,too-many-branches,too-many-statements,too-many-return-statements
    team, project, _redirect = check_the_team_and_project_are_existed(
        pid=pid, tid=tid)
    if _redirect:
        return _redirect

    is_admin = (g.user['account']['_id'] in team['chiefs'] or
                g.user['account']['_id'] in team['owners'] or
                g.user['account']['_id'] in project['owners'])

    if not is_admin:
        return redirect('/')

    campaign_data = SenderCampaign.get(
        cid=cid, pid=team['pid'], tid=team['tid'])
    if request.method == 'GET':
        return render_template('./sender_campaign_schedule.html', campaign=campaign_data, team=team)

    if request.method == 'POST':
        data = request.get_json()

        if 'casename' in data and data['casename'] == 'getlogs':
            logs = []
            for log in SenderLogs.get(cid=cid):
                logs.append({
                    'time': arrow.get(log['create_at']).to(
                            'Asia/Taipei').format('YYYY-MM-DD HH:mm:ss'),
                    'cid': log['cid'],
                    'count': len(log['receivers']),
                    'layout': log['layout'],
                    'desc': log['desc'],
                })

            return jsonify({'logs': logs})

        if 'casename' in data and data['casename'] == 'send':
            user_datas = []

            fields, raws = SenderReceiver.get_from_user(
                pid=team['pid'], tids=campaign_data['receiver']['teams'])
            for raw in raws:
                user_datas.append(dict(zip(fields, raw)))

            fields, raws = SenderReceiver.get(pid=team['pid'], cid=cid)
            for raw in raws:
                user_datas.append(dict(zip(fields, raw)))

            if 'team_w_tags' in campaign_data['receiver'] and \
                    team['tid'] in campaign_data['receiver']['team_w_tags'] and \
                    campaign_data['receiver']['team_w_tags'][team['tid']]:
                fields, raws = SenderReceiver.get_by_tags(
                    pid=team['pid'], tid=team['tid'],
                    tags=campaign_data['receiver']['team_w_tags'][team['tid']])

                for raw in raws:
                    user_datas.append(dict(zip(fields, raw)))

            if campaign_data['receiver']['all_users']:
                fields, raws = SenderReceiver.get_all_users()
                for raw in raws:
                    user_datas.append(dict(zip(fields, raw)))

            SenderLogs.save(cid=cid,
                            layout=campaign_data['mail']['layout'],
                            desc='Send', receivers=user_datas)

            source = None
            if campaign_data['mail']['layout'] == '2':
                if 'mailling' in team and team['mailling']:
                    source = {'name': team['name'], 'mail': team['mailling']}
                    if not (source['name'].startswith('COSCUP') or
                            source['name'].startswith('coscup')):
                        source['name'] = f"COSCUP {source['name']}"
                else:
                    source = {'name': 'COSCUP Attendee',
                              'mail': 'attendee@coscup.org'}

            sender_mailer_start.apply_async(kwargs={
                'campaign_data': campaign_data, 'team_name': team['name'], 'source': source,
                'user_datas': user_datas, 'layout': campaign_data['mail']['layout']})

            return jsonify(data)

        if 'casename' in data and data['casename'] == 'sendtest':
            # layout, campaign_data, team, uids
            user_datas = []

            fields, raws = SenderReceiver.get_from_user(
                pid=team['pid'], tids=campaign_data['receiver']['teams'])
            if raws:
                user_datas.append(dict(zip(fields, random.choice(raws))))

            fields, raws = SenderReceiver.get(pid=team['pid'], cid=cid)
            if raws:
                user_datas.append(dict(zip(fields, random.choice(raws))))

            if 'team_w_tags' in campaign_data['receiver'] and \
                    team['tid'] in campaign_data['receiver']['team_w_tags'] and \
                    campaign_data['receiver']['team_w_tags'][team['tid']]:
                fields, raws = SenderReceiver.get_by_tags(
                    pid=team['pid'], tid=team['tid'],
                    tags=campaign_data['receiver']['team_w_tags'][team['tid']])
                if raws:
                    user_datas.append(dict(zip(fields, random.choice(raws))))

            if campaign_data['receiver']['all_users']:
                fields, raws = SenderReceiver.get_all_users()
                if raws:
                    user_datas.append(dict(zip(fields, random.choice(raws))))

            uid = g.user['account']['_id']
            users = User.get_info(uids=[uid, ])

            for user_data in user_datas:
                user_data.update({
                    'mail': users[uid]['oauth']['email'],
                })

            SenderLogs.save(cid=cid,
                            layout=campaign_data['mail']['layout'],
                            desc='Test Send', receivers=user_datas)

            source = None
            if campaign_data['mail']['layout'] == '2':
                if 'mailling' in team and team['mailling']:
                    source = {'name': team['name'], 'mail': team['mailling']}
                    if not (source['name'].startswith('COSCUP') or
                            source['name'].startswith('coscup')):
                        source['name'] = f"COSCUP {source['name']}"
                else:
                    source = {'name': 'COSCUP Attendee',
                              'mail': 'attendee@coscup.org'}

            sender_mailer_start.apply_async(kwargs={
                'campaign_data': campaign_data, 'team_name': team['name'], 'source': source,
                'user_datas': user_datas, 'layout': campaign_data['mail']['layout']})

            return jsonify(data)

    return jsonify({}), 404
