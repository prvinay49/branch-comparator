import os
import sys
import json
import time
from datetime import datetime, timedelta
from JiraAutomation import *
from rmGerritUtils import * 
from report_html import html

def add_values_in_dict(sample_dict, key, list_of_values):
    ''' Append multiple values to a key in 
        the given dictionary '''
    if key not in sample_dict:
        sample_dict[key] = list()
    sample_dict[key].extend(list_of_values)
    return sample_dict
    
    

class Automerger2:
    def __init__(self,  issues, src , dst):
        self.target = dst
        self.Issues = issues
        self.source = src
        #self.gerrit_topic  = gerrit_topic
        with open(BASE_DIR+'/config/manifests.json', 'r') as manifest_file:
            manifests = json.load(manifest_file)

        self.manifest_projects = [m['project'] for m in manifests.values()]

        self.gerrit = gerrit_login('primary_gerrit')
        self.cherry_picked_list  = []
        self.IssuesDictwithTopic = {}
        self.IssuesDictwithTopic_ChangeId = {}
        self.sortedIssueQueue = []
        
        self.merge_conflict_list = []
        #self.change_id_reults = {}
        self.triggered_projects = []
        self.triggered_list = []
        self.rebase_failed_list = []
        self.squash_list = []
        self.already_triggered_projects = []
        self.inprogress_gerrits = []

        self.merge_conflict_mailids = []
        self.rebase_failed_mailids = []
        self.squash_mailids = []
        self.cherry_picked_project_list = []
        self.ticket_move_to_RRT = []
        
       
        
    def get_gerrit_changeId_by_topic(self, gerrit_topic):
        #change_id_gerrits = self.gerrit.get('/changes/?q=topic:%s+(status:merged)' %(gerrit_topic))
        change_id_gerrits = self.gerrit.get('/changes/?q=topic:%s+(status:merged)&o=CURRENT_REVISION&o=CURRENT_COMMIT&o=MESSAGES' %(gerrit_topic))
        #print(change_id_gerrits)
        change_id = []
        for i in range(len(change_id_gerrits)):
            change_id.append(change_id_gerrits[i]) 
            #print(self.check_already_in_target(change_id_gerrits[i]))
        #print(change_id)
        # to do return only if not available 
        return change_id
        
        
        
    def getGerrittopicsfromIssues(self):
        for issue in self.Issues:
            try:
                gerrit_topic = str(jira.getGerritTopicByIssue(issue))
                print('gerrit topic ', gerrit_topic)
                findIndex = gerrit_topic.find('Gerrit_Topic_Name:')
                if findIndex  != -1:
                    gerrit_topic = gerrit_topic[findIndex:]
                    gerrit_topic = gerrit_topic.replace('Gerrit_Topic_Name:','').replace(" ", "")
                    self.IssuesDictwithTopic[issue] = gerrit_topic
            except Exception as e:
                print('Exception:', str(e))
            print(self.IssuesDictwithTopic)
            
    def mapIssuewithTopicAndChangeId(self):
        for key, value  in self.IssuesDictwithTopic.items(): 
            topic_changeId =  self.get_gerrit_changeId_by_topic(value)
            #print('######',topic_changeId, value  )
            self.IssuesDictwithTopic_ChangeId = add_values_in_dict(self.IssuesDictwithTopic_ChangeId, key, [value, topic_changeId])
            
        #print('Issues dict ',self.IssuesDictwithTopic_ChangeId)
    
    def sortIssuesAsperMergetime(self):
        print(self.IssuesDictwithTopic_ChangeId.keys())
        for key, value in self.IssuesDictwithTopic_ChangeId.items():
            change_id_gerrits = value[1]                
            if change_id_gerrits: 
                merge_timing = []
                for i in range(len(change_id_gerrits)):
                    merge_timing.append(str (datetime.strptime(change_id_gerrits[i]['submitted'].split('.')[0], '%Y-%m-%d %H:%M:%S')))
                merge_timing.sort(key=lambda date:datetime.strptime(date,"%Y-%m-%d %H:%M:%S"))
                latest_merge_timing = merge_timing[-1]
                self.sortedIssueQueue.append([key, latest_merge_timing])
            else:
                print(' topic dont have change id ', key )

        self.sortedIssueQueue = sorted(self.sortedIssueQueue, key = lambda  date:datetime.strptime(date[1], '%Y-%m-%d %H:%M:%S'))
        print('sorted    ', self.sortedIssueQueue)
      
    def processchangeIds(self):
        for index in self.sortedIssueQueue:
            value = self.IssuesDictwithTopic_ChangeId[index[0]]
            try:
                change_id_gerrits = value[1]  
                iterator = 0
                temp = []
                for i in range(len(change_id_gerrits)):
                    changeInTarget = self.check_already_in_target(change_id_gerrits[i])
                    print('changes in ', changeInTarget)
                    if changeInTarget == 'Not available' :
                        print('cherry pick ')
                        #self.cherry_pick(change_id_gerrits[i])
                    else:
                        print('skip')
                        iterator = iterator +1
                        gerritTopicChangeId = self.get_gerrit_topic( change_id_gerrits[i]['change_id'])
                        if gerritTopicChangeId == None:
                            print('skipping as changes are not merged in stable2')
                            iterator = iterator -1
                        elif 'topic' in gerritTopicChangeId['topic_gerrit'].keys():
                            temp.append(gerritTopicChangeId['topic_gerrit']['topic'])
                        else:
                            temp.append(gerritTopicChangeId['topic_gerrit']['_number'])
                        
                if iterator == len(change_id_gerrits):
                    print(' skipping the changes as all the changes are already part of stable2')
                    jira.changeStateOfIssue(index[0])
                    self.ticket_move_to_RRT.append([index[0],list(set(temp))])
                    #print(type(index[0]))
                else:
                    print('cherry pick ')
                    self.cherry_pick_gerrit(change_id_gerrits)
                    
            except Exception as e:
                print('Exception:', str(e))
            
    def do_submit(self, s_gerrit, commit_id, submit=False):
        ## code review +2 already applied or not
        review_data = {'labels': {'Code-Review': 2}}
        # print('/changes/{0}/revisions/{1}/{2}'.format(s_gerrit, commit_id, submit))
        # return '/changes/{0}/revisions/{1}/{2}'.format(s_gerrit, commit_id, submit)
        try:
            if submit:
                self.gerrit.post('/changes/{0}/revisions/{1}/{2}'.format(s_gerrit, commit_id, submit))
                print('Triggered action "%s" for "%s", "%s"' %(submit, s_gerrit, commit_id))
                print('*********************************************', "\n")
            else:
                print('Triggered action "Code review +2" for "%s", "%s"' % (s_gerrit, commit_id))
                self.gerrit.post('/changes/{0}/revisions/{1}/review'.format(s_gerrit, commit_id), json=review_data)
        except Exception as e:
            print('Error occurred while review/submit.', e)
            

    def rebase_gerrit(self, togerrit):
        try:
            rebased_gerrit = self.gerrit.post('/changes/%s/rebase'%(str(togerrit['_number'])), json={'base': ''})
            print('Rebased successfully...', togerrit['_number'], togerrit['change_id'])
            return rebased_gerrit, True
        except Exception as e:
            # print(e)
            if e and 'change is already up to date.' in e.response.text.lower():
                print('Change is already up to date.')
                return togerrit, True
            else:
                return togerrit, False
    def check_already_in_target(self, tgt):
        pre_check = self.gerrit.get('/changes/?q=branch:%s+%s&o=CURRENT_REVISION&o=CURRENT_COMMIT&o=MESSAGES'
                                    % (self.target, tgt['change_id']))
        if pre_check:
            if type(pre_check) is dict:
                pre_check = [pre_check]

            if self.check_triggered_time(tgt['_number']) is False:
                rebased_gerrit, reb_result = self.rebase_gerrit(pre_check[0])
                if reb_result is False:
                    print("Rebase failed for '%s', '%s'" % (tgt['_number'], tgt['change_id']))
                    if tgt['status'] == 'MERGED':
                        return {'gerrit': pre_check[0], 'new_commit': pre_check[0]['current_revision']}
                    else:
                        return {'status': False, 'reason': 'Rebase failed'}
                else:
                    print('Change id already exist in target',
                          tgt['change_id'], pre_check[0]['current_revision'])
            else:
                print('Already build inprogress for ')
                return {'status': False, 'reason': 'Build in progress'}

            return {'gerrit': pre_check[0], 'new_commit': pre_check[0]['current_revision']}
        else:
            return 'Not available'
        
    
    def get_gerrit_topic(self, change_id):
        
        topic_gerrits = self.gerrit.get('/changes/?q=branch:%s+status:merged+change:%s&o=CURRENT_REVISION&o=CURRENT_COMMIT&o=MESSAGES'
                                        %(self.target, change_id))

        if len(topic_gerrits) > 1:
            print('************Alert more than one topic list %s******************' % (topic_gerrits))

        result = {
            'cherrypick': True,
            'topic_gerrit': None
        }

        if not topic_gerrits:
            print('********* Alert: Empty topic gerrit for: *********', change_id)
            return None

        result['topic_gerrit'] = topic_gerrits[0]
        # print(result)
        return result
    
       
    def get_build_options(self, gerrit_id, commit_id):
        res = self.gerrit.get('/changes/%s/revisions/%s/actions' %(gerrit_id, commit_id))
        if res.get('cionetrigger~set-ci') and \
                res.get('cionetrigger~set-ci').get('enabled') is True:
            if res.get('cionetrigger~set-ci').get('label') == 'Trigger Verification':
                return ('cionetrigger~set-ci', 'Trigger Verification')
            elif res.get('cionetrigger~set-ci').get('label') == 'Trigger Verification And Submit':
                return ('cionetrigger~set-ci', 'Trigger Verification And Submit')
            elif res.get('cionetrigger~set-ci').get('label') == 'Submit After Rebuild And CI':
                rebase_result = self.rebase_gerrit_by_id(gerrit_id)
                if rebase_result is False:
                    return (False, 'Rebase Failed')
                else:
                    return ('cionetrigger~set-ci', 'Submit After Rebuild And CI')
                #     if res.get('citest~set-ci').get('label') == 'Submit After CI':
                #         return 'citest~set-ci'
                # else:
                #     if rebase_result != 'Conflict':
                #         return 'cionetrigger~set-ci'
        return (False, 'No option')

    def add_to_already_tgr_projects(self, merged_result, action):
        for mgr in merged_result:
            if mgr.get('gerrit'):
                mgr = mgr.get('gerrit')
            self.already_triggered_projects.append(
                {'gerrit_id': mgr.get('_number'),
                 'commit_id': mgr.get('current_revision') or mgr.get('new_commit') ,
                 'project': mgr.get('project'),
                 'change_id': mgr.get('change_id'),
                 'action': action, 'topic': mgr.get('topic')
                 })

    def add_to_already_inprogress(self, glist):
        for mgr in glist:
            self.inprogress_gerrits.append(
                {'gerrit_id': mgr.get('_number') or mgr.get('gerrit').get('_number'),
                 'commit_id': mgr.get('current_revision') or mgr.get('new_commit'),
                 'project': mgr['project'], 'change_id': mgr.get('change_id') or mgr.get('gerrit').get('change_id'),
                 'action': 'Already inprogress', 'topic': mgr.get('topic')
                 })

    def cherrypick_revert(self):
        tg_gerrit_id_list = [jg['gerrit_id'] for jg in self.triggered_list]
        for cg in self.cherry_picked_list:
            if cg[0] not in tg_gerrit_id_list:
                self.code_review_reject(cg[0], cg[1])

    def check_triggered_time(self, gerrit_id, commit_id=None, change_id=None):
        print('Checking last trigger time for %s' %(gerrit_id))
        time_range = datetime.now().replace(microsecond=0) - timedelta(hours=3, minutes=0)
        res = self.gerrit.get('/changes/%s/detail' % (gerrit_id))
        if res.get('messages'):
            for meg in res.get('messages'):
                if meg['message'].find('Please find details about started builds here') !=-1:
                    meg_time = datetime.strptime(meg['date'].split('.')[0], '%Y-%m-%d %H:%M:%S')
                    print('Last build time:', meg_time, time_range)
                    if meg_time > time_range:
                        print('Triggered within 3 hrs', gerrit_id)
                        return True
        return False
        
    def add_to_trigger_list(self, merged_result, action):
        for mgr in merged_result:
            self.triggered_list.append(
                {'gerrit_id': mgr['gerrit']['_number'],
                 'commit_id': mgr['gerrit'].get('current_revision') or mgr.get('new_commit'),
                 'project': mgr['gerrit']['project'], 'change_id': mgr['gerrit']['change_id'],
                 'action': action, 'topic': mgr['gerrit'].get('topic')
                 })

    def code_review_reject(self, s_gerrit, commit_id):
        ## if -1 already available remove
        review_data = {'labels': {'Code-Review': -1}}
        print('Applying -1 for %s, %s' %(s_gerrit, commit_id))
        try:
            self.gerrit.post('/changes/{0}/revisions/{1}/review'.format(s_gerrit, commit_id), json=review_data)
            print("Code review -1 applied for %s %s" %(s_gerrit, commit_id))
            return "Code review -1 applied for %s %s" %(s_gerrit, commit_id)
        except Exception as e:
            print('Error occurred while appply -1.', e)


    def cherry_pick_gerrit(self, gerrit_list):
        print("\n", '********** Cherry picking gerrit list *******')
        merged_result = []
        error_result = []
        merge_change_ids = []
        project_list = []
        for tgc in gerrit_list:
            merge_change_ids.append(tgc['change_id'])
            if tgc['project'] in project_list:
                for cid in gerrit_list:
                    squash_owner = list(cid['revisions'].values())[0]['commit']['author']['email']
                    self.squash_list.append((cid['_number'], cid['change_id'], cid['project'], cid.get('topic'), squash_owner))
                    self.squash_mailids.append(squash_owner)
                print("Gerrits in same projcet please squash" \
                       " the changes %s Change ids %s" %(tgc['change_id'], merge_change_ids))
                return
            if tgc['project'] in self.triggered_projects or tgc['project'] in self.cherry_picked_project_list :
                self.add_to_already_tgr_projects(gerrit_list, 'Already triggered project or skipping it for next iteration ')
                return
            elif tgc['project'] in self.manifest_projects:
                print('Project "%s" is manifest project, Change Id: %s'
                      % (tgc['project'], tgc['change_id']))
                # No need to cherry pick
                self.add_to_already_tgr_projects(gerrit_list, 'manifest project')
                return
            else:
                project_list.append(tgc['project'])
        if merge_change_ids:
            print('Cherrypick and build process started for change ids: %s, Topic: %s'
                  %(merge_change_ids, gerrit_list[0].get('topic')))
        for tg in gerrit_list:
            res = self.check_already_in_target(tg)
            if res == 'Not available':
                res = self.cherry_pick(tg)
            # print(res, "**********************************************")
            if res.get('status') is False or res.get('gerrit') is None:
                print('Cannot trigger build for Change ids: "%s"' % (merge_change_ids))
                error_result.append('cherrypick failed')
                if res.get('reason') == 'Build in progress':
                    self.add_to_already_inprogress(gerrit_list)
                if res.get('reason') == 'Rebase failed':
                    for tgtr in gerrit_list:
                        rebase_owner = list(tgtr['revisions'].values())[0]['commit']['author']['email']
                        self.rebase_failed_list.append(
                            (tgtr['_number'], tgtr['change_id'], tgtr['project'], tgtr.get('topic'), rebase_owner))
                        self.rebase_failed_mailids.append(rebase_owner)
                    return
                else:
                    for cgtm in gerrit_list:
                        merge_owner = list(cgtm['revisions'].values())[0]['commit']['author']['email']
                        self.merge_conflict_list.append(
                            (cgtm['_number'], cgtm['change_id'], cgtm['project'], cgtm.get('topic'), merge_owner))
                        self.merge_conflict_mailids.append(merge_owner)
                    print("Cherry pick failed for %s, %s and result is %s" %(tg['_number'], tg['change_id'], res))
                return
            else:
                merged_result.append(res)
        if merged_result and not error_result:
            build_options = []
            for mg in merged_result:
                commit_id = mg['gerrit'].get('current_revision') or mg.get('new_commit')
                print("Waiting 1 sec and Checking build options and applying code review +2 started:", mg['gerrit']['_number'], commit_id)
                time.sleep(1)
                self.do_submit(mg['gerrit']['_number'], commit_id)
                print('\n' "Code review +2 applied")
                # print('*********************************************')
                res = self.get_build_options(mg['gerrit']['_number'], commit_id)
                build_options.append(res)
                if False in res:
                    if res[1] == 'Rebase Failed':
                        print("Rebase failed for '%s', '%s'" % (mg['gerrit']['_number'], mg['gerrit']['change_id']))
                        for mgtr in merged_result:
                            rebase_owner = list(mgtr['revisions'].values())[0]['commit']['author']['email']
                            self.rebase_failed_list.append(
                                (mgtr['gerrit']['_number'], mgtr['gerrit']['change_id'],
                                 mgtr['gerrit']['project'], mgtr['gerrit'].get('topic'), rebase_owner))
                            self.rebase_failed_mailids.append(rebase_owner)
                    else:
                        self.add_to_already_tgr_projects(merged_result, 'Build options not available')

                else:
                    print('Build option for gerrit "%s": "%s"' %(mg['gerrit']['_number'], res[1]))
            if False not in [reb[0] for reb in build_options]:
                # bc = 0
                mg = merged_result[0]
                project_name = mg['gerrit']['project']
                commit_id = mg['gerrit'].get('current_revision') or mg.get('new_commit')
                print('Submitting action "%s" for change id: "%s" and gerrit "%s" '
                      %(build_options[0][1], mg['gerrit']['change_id'], mg['gerrit']['_number']))
                if project_name not in self.triggered_projects:
                    if self.check_triggered_time(mg['gerrit']['_number']) is False:
                        self.do_submit(mg['gerrit']['_number'],commit_id, build_options[0][0])
                        self.triggered_projects.append(project_name)
                        self.add_to_trigger_list(merged_result, build_options[0][1])
                    else:
                        self.add_to_already_inprogress(gerrit_list)
                else:
                    self.add_to_already_tgr_projects(gerrit_list, 'Already triggered project')
            print('********************Process finished*************************')
            
    def get_comments(self, gerrit_id, commit_id=None, change_id=None):
        res = self.gerrit.get('/changes/%s/detail' % (gerrit_id))
        replace_text = 'Please find details about started builds here'
        build_url = ""
        if res.get('messages'):
            build_found = False
            for meg in res.get('messages'):
                if meg['message'].find(replace_text) != -1:
                    find_chr = meg['message'].find('https')
                    build_url = meg['message'][find_chr:].split('\n')[0]
                    print('Jenkins build triggered:%s for %s' %(build_url, gerrit_id))
                    build_found = True
                    #return build_url
            if build_found is False:
                print('Unable to find the jenkins build details')
        if not build_url:
            return 'Unable to find the jenkins build details'
        else:
            return build_url
     
            
            
    def cherry_pick(self, cgt):
        time.sleep(3)
        url = '/changes/{0}/revisions/{1}/cherrypick'
        message = cgt['revisions'][cgt['current_revision']]['commit']['message']
        post_data = {
            'message': message,
            'destination': self.target
        }
        try:
            result = self.gerrit.post(url.format(cgt['id'],
                                                 cgt['current_revision']),
                                      json=post_data, timeout = 50)
        except Exception as e:
            result = None
            print('Exception:', e)
            if e and 'merge conflict' in e.response.text.lower() or 'conflict'in e.response.text.lower()\
                    or 'conflict' in str(e):
                return {'status': False, 'gerrit': None, 'new_commit': None}
            else:
                if e and not 'change is already up to date' in e.response.text.lower():
                    return {'status': False, 'gerrit': None, 'new_commit': None}

        new_commit_res = self.gerrit.get('/changes/?q=branch:%s+%s&o=CURRENT_REVISION&o=CURRENT_COMMIT&o=MESSAGES'
                                         %(self.target, cgt['change_id']))

        if new_commit_res:
            new_commit = new_commit_res[0]['current_revision']
        else:
            new_commit = None
            print('No new commit %%%%%%%%%%%%%%%%%%%%%%%%',new_commit_res, cgt['change_id'])
        self.cherry_picked_project_list.append(cgt['project'])
        self.cherry_picked_list.append((result['_number'], result.get('current_revision') or new_commit))
        time.sleep(3)
        return {'status': True, 'gerrit': result, 'new_commit': new_commit}

    def generate_html_report(self, html):
        merge_conflict_html = ''
        rebase_failed_html = ''
        squash_html = ''
        sno = 1

        html += '''<h4>Triggered List</h4><table class="custom-table">
        <thead><tr><th>S.no.</th><th>Gerrit</th>
        <th>Change Id</th><th>Project</th><th>Topic</th><th>Status</th><th>Build Url</th>
        </tr></thead><tbody>'''

        for tgrg in self.triggered_list:
            html += "<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td><td>{4}</td><td class=\"success\">{5}</td><td>{6}</td></tr>".format(
                sno, tgrg['gerrit_id'], tgrg['change_id'], tgrg['project'], tgrg['topic'],
                tgrg['action'], tgrg['build_url'])
            sno += 1
        html += "</tbody></table><hr/>"



        merge_conflict_html = '''<h4>Merge Coflict</h4><table class="custom-table"><thead><tr><th>S.no</th><th>Gerrit</th>
        <th>Change Id</th><th>Project</th><th>Topic</th><th>Status</th><th>Owner</th></tr></thead><tbody>'''

        for tmg in self.merge_conflict_list:
            merge_conflict_html += '''<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td><td>{4}</td>
            <td class="failure">Merge Conflict</td><td>{5}</td></tr>'''.format(
                sno, tmg[0], tmg[1], tmg[2], tmg[3], tmg[4]
            )
            sno += 1
        merge_conflict_html += "</tbody></table><hr/>"

        html += merge_conflict_html

        rebase_failed_html += '''<h4>Rebase failed</h4><table class="custom-table">
        <thead><tr><th>S.no.</th><th>Gerrit</th>
        <th>Change Id</th><th>Project</th><th>Topic</th><th>Status</th><th>Owner</th></tr></thead><tbody>'''

        for trg in self.rebase_failed_list:
            rebase_failed_html += '''<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td><td>{4}</td>
            <td class="failure">Rebase failed</td><td>{5}</td></tr>'''.format(
                sno, trg[0], trg[1], trg[2], trg[3], trg[4]
            )
            sno += 1
        rebase_failed_html += "</tbody></table><hr/>"

        html += rebase_failed_html

        squash_html += '''<h4>Squash change</h4><table class="custom-table">
        <thead><tr><th>S.no.</th><th>Gerrit</th><th>Change Id</th><th>
        Project</th><th>Topic</th><th>Status</th><th>Owner</th></tr></thead><tbody>'''

        for tsg in self.squash_list:
            squash_html += '''<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td><td>{4}</td>
            <td class="failure">Squash the changes</td><td>{5}</td></tr>'''.format(
                sno, tsg[0], tsg[1], tsg[2], tsg[3], tsg[4]
            )
            sno += 1
        squash_html += "</tbody></table><hr/>"

        html += squash_html

        html += '''<h4>Not Triggered List(Project already triggered)</h4>
        <table class="custom-table"><thead><tr><th>S.no.</th><th>Gerrit</th>
        <th>Change Id</th><th>Project</th><th>Topic</th><th>Status</th>
        </tr></thead><tbody>'''

        for tprg in self.already_triggered_projects:
            html += "<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td><td>{4}</td><td class=\"success\">{5}</td></tr>".format(
                sno, tprg['gerrit_id'], tprg['change_id'], tprg['project'], tprg['topic'], tprg['action'])
            sno += 1
        html += "</tbody></table><hr/>"

        html += '''<h4>Not Triggered List(Already Build inprogress)</h4>
                <table class="custom-table"><thead><tr><th>S.no.</th><th>Gerrit</th>
                <th>Change Id</th><th>Project</th><th>Topic</th><th>Status</th>
                </tr></thead><tbody>'''

        for tirg in self.inprogress_gerrits:
            html += "<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td><td>{4}</td><td class=\"success\">{5}</td></tr>".format(
                sno, tirg['gerrit_id'], tirg['change_id'], tirg['project'], tirg['topic'], tirg['action'])
            sno += 1
        html += "</tbody></table><hr/>"

        html += "</body></html>"
        
        html += '''<h4>Ticket moved to Ready for Release test (changes merged in stable2)</h4>
                <table class="custom-table"><thead><tr><th>S.no.</th><th>Ticket</th><th>Topic</th>
                <th>Resolution</th><th>Status</th>
                </tr></thead><tbody>'''
                       
        for tickets, topic  in self.ticket_move_to_RRT:
            html += "<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td><td>{4}</td>".format(
                sno,tickets ,topic, 'Ready for Release test ', 'Merged')
            sno += 1
        html += "</tbody></table><hr/>"

        html += "</body></html>"
        
        
        mail_html = '%s%s%s'%(merge_conflict_html, rebase_failed_html, squash_html)

        return html, mail_html


if __name__ == '__main__':
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    args_length = len(sys.argv)
    
    print('Usage: python main.py <source_branch> <destination_branch> <device_profile> ')
    
    print('topic format Gerrit_Topic_Name:topicfromsprint')

    jira = JiraAutomation('jira')
    
    with open(BASE_DIR + '/config/config.json', 'r') as config_file:
        devices_config = json.load(config_file)
        
    with open(BASE_DIR + '/config/devices.json', 'r') as devices_file:
        all_devices = json.load(devices_file)
    source_sprint = sys.argv[1].lower() 
    dest_stable2  = sys.argv[2].lower() 
    devices = []
    if args_length == 4:
        device_profile = sys.argv[3].lower()
    else:
        device_profile = 'rdkall'

    if device_profile == 'rdkall':
        for device in all_devices.values():
            devices += device
    elif device_profile == 'rdkv':
        devices = all_devices.get('rdkv_devices')
        device  = 'rdkv_devices'
    elif device_profile == 'rdkb':
        devices = all_devices.get('rdkb_devices')
        device  = 'rdkb_devices'
    elif device_profile == 'rdkc':
        devices = all_devices.get('xhome_devices')
        device  = 'xhome_devices'
        
    device_filter = []    
    if device_profile == 'rdkall':
        for device in all_devices.keys():
            device_config = devices_config[device]
            device_filter.append( device_config[0]['filter']  )
    else :    
        device_config = devices_config[device]
        device_filter.append( device_config[0]['filter'])
    
    device_filter = list(set(device_filter))
    issuesListfromFilter = []
    for filters in device_filter:
        issuesDict= jira.getIssuesByFilter(filters)
        for issue in issuesDict:
            print('{}:     {}'.format(issue.key, issue.fields.summary))
            if str(issue.fields.issuetype) == 'Bug' or  str(issue.fields.issuetype) == 'Task' :
                    if str(issue.fields.resolution) == 'RM Approved':
                        issuesListfromFilter.append(str(issue.key))
                
                
    issuesListfromFilter = list(set(issuesListfromFilter))
    print(issuesListfromFilter)
    
    
    try : 
        automerger2  = Automerger2(issuesListfromFilter, source_sprint ,dest_stable2 )
        automerger2.getGerrittopicsfromIssues()
        automerger2.mapIssuewithTopicAndChangeId()
        automerger2.sortIssuesAsperMergetime()
        
        automerger2.processchangeIds()
    
    except Exception as e:
        print('Exception:', str(e))
    
    finally:
        print("Merge conflict list:", automerger2.merge_conflict_list, "\n")
        print("Rebase failed list:", automerger2.rebase_failed_list, "\n")
        print('Cherrypicked list:', automerger2.cherry_picked_list, "\n")
        print('Squashed list:', automerger2.squash_list, "\n")
        print("Triggered gerrits:", automerger2.triggered_list, "\n")
        print("Already build inprogress gerrits:", automerger2.inprogress_gerrits, "\n")
        print("Already triggered for project gerrits:", automerger2.already_triggered_projects, "\n")

        mail_file_name = BASE_DIR + '/reports/{0}_{1}_build_mail_list_{2}.txt'.format(
            automerger2.source, automerger2.target,
            datetime.now().strftime('%d_%m_%Y_%H_%M_%S')
        )

        mail_file_name1 = BASE_DIR + '/reports/{0}_{1}_build_mail_list.txt'.format(
            automerger2.source, automerger2.target
        )

        mail_str = ','.join(list(set(automerger2.merge_conflict_mailids)))
        mail_str += ','.join(list(set(automerger2.rebase_failed_mailids)))
        mail_str += ','.join(list(set(automerger2.squash_mailids)))
        
        
      
        print(mail_str)

        
        
        with open(mail_file_name, 'w') as f:
            f.write(mail_str)
        with open(mail_file_name1, 'w') as f1:
            f1.write(mail_str)

    print('********************** Waiting for 3 mins to get the gerrit comments*****************************')
    time.sleep(300)
    
    tgl_index = 0
    for tgl in automerger2.triggered_list:
        # automerger2.get_comments('461680')
        build_url = automerger2.get_comments(tgl['gerrit_id'])
        automerger2.triggered_list[tgl_index]['build_url'] = build_url
        tgl_index += 1

    report_html, mail_html = automerger2.generate_html_report(html)

    report_file_name = BASE_DIR + '/reports/{0}_{1}_build_report_{2}.html'.format(
        automerger2.source, automerger2.target,
        datetime.now().strftime('%d_%m_%Y_%H_%M_%S')
    )
    new_report_name = BASE_DIR + '/reports/{0}_{1}_build_report.html'.format(
        automerger2.source, automerger2.target)

    # merge_mail_file_name = '/reports/{0}_{1}_build_merge_mail_body_{2}.html'.format(
    #     automerger2.source, automerger2.target,
    #     datetime.now().strftime('%d_%m_%Y_%H_%M_%S')
    # )
    # merge_mail_file_name1 = '/reports/{0}_{1}_build_merge_mail_body.html'.format(
    #     automerger2.source, automerger2.target)
    #
    # with open(BASE_DIR + merge_mail_file_name, 'w') as fma:
    #     fma.write(mail_html)
    #
    # with open(BASE_DIR + merge_mail_file_name1, 'w') as fma1:
    #     fma1.write(mail_html)

    print('Report file path:%s%s' %(BASE_DIR, report_file_name))

    with open(new_report_name, 'w') as fsa:
        fsa.write(report_html)

    with open( report_file_name, 'w') as fna:
        fna.write(report_html)
        
        
    # to do move the tickets to ready for release test
    
    #jira.changeStateOfIssue('issue')
    
    
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
