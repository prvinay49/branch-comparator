
from rmJiraUtils import *

class JiraAutomation():
    def __init__(self,  jira_key):
        self.jira = jira_login()

    def getGerritTopicByIssue(self, issue ):
        issue = self.jira.issue(issue)
        print('issue key ',issue.key)
        print(issue.raw['fields']['customfield_28345'])
        gerrit_topic = str(issue.raw['fields']['customfield_28345'])
        return gerrit_topic

    def getIssuesByFilter(self, filter ):
        print("getIssuesByFilter:")
        jql = self.jira.filter(filter).jql
        issuesDict = self.jira.search_issues(jql)
        for issue in issuesDict:
            print('{}: {}'.format(issue.key, issue.fields.summary))
        return issuesDict

    def checkRMApprovedState(self, issue):
        flag = False
        if self.jira.issue(issue).fields.resolution == 'RM Approved':
            flag = True
        return flag  
       
    def changeStateOfIssue(self, issue):
        #transistion = self.jira.transitions(issue)
        self.jira.transition_issue(issue,'81')

