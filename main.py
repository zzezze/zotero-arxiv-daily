import arxiv
import argparse
import os
from pyzotero import zotero
from recommender import rerank_paper
from construct_email import render_email
import requests
import datetime
import re
from time import sleep
from email.header import Header
from email.mime.text import MIMEText
from email.utils import parseaddr, formataddr
import smtplib

def get_zotero_corpus(id:str,key:str) -> list[dict]:
    zot = zotero.Zotero(id, 'user', key)
    corpus = zot.everything(zot.items(itemType='conferencePaper || journalArticle || preprint'))
    corpus = [c for c in corpus if c['data']['abstractNote'] != '']
    return corpus

def get_paper_code_url(paper:arxiv.Result) -> str:
    retry_num = 5
    while retry_num > 0:
        try:
            paper_list = requests.get(f'https://paperswithcode.com/api/v1/papers/?arxiv_id={paper.arxiv_id}').json()
            break
        except:
            sleep(1)
            retry_num -= 1
            if retry_num == 0:
                return None
    
    if paper_list.get('count',0) == 0:
        return None
    paper_id = paper_list['results'][0]['id']
    retry_num = 5
    while retry_num > 0:
        try:
            repo_list = requests.get(f'https://paperswithcode.com/api/v1/papers/{paper_id}/repositories/').json()
            break
        except:
            sleep(1)
            retry_num -= 1
            if retry_num == 0:
                return None
    if repo_list.get('count',0) == 0:
        return None
    return repo_list['results'][0]['url']

def get_arxiv_paper(query:str, start:datetime.datetime, end:datetime.datetime) -> list[arxiv.Result]:
    client = arxiv.Client()
    search = arxiv.Search(query=query, sort_by=arxiv.SortCriterion.SubmittedDate)
    papers = []
    for i in client.results(search):
        published_date = i.published
        if published_date < end and published_date >= start:
            i.arxiv_id = re.sub(r'v\d+$', '', i.get_short_id())
            i.code_url = get_paper_code_url(i)
            papers.append(i)
        elif published_date < start:
            break
    return papers

def send_email(sender:str, receiver:str, password:str,smtp_server:str,smtp_port:int, html:str,):
    def _format_addr(s):
        name, addr = parseaddr(s)
        return formataddr((Header(name, 'utf-8').encode(), addr))

    msg = MIMEText(html, 'html', 'utf-8')
    msg['From'] = _format_addr('Github Action <%s>' % sender)
    msg['To'] = _format_addr('You <%s>' % receiver)
    today = datetime.datetime.now().strftime('%Y/%m/%d')
    msg['Subject'] = Header(f'Daily arXiv {today}', 'utf-8').encode()

    server = smtplib.SMTP(smtp_server, smtp_port)
    server.starttls()
    server.login(sender, password)
    server.sendmail(sender, [receiver], msg.as_string())
    server.quit()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Recommender system for academic papers')
    parser.add_argument('--zotero_id', type=str, help='Zotero user ID',default=os.environ.get('ZOTERO_ID'))
    parser.add_argument('--zotero_key', type=str, help='Zotero API key',default=os.environ.get('ZOTERO_KEY'))
    parser.add_argument('--arxiv_query', type=str, help='Arxiv search query',default=os.environ.get('ARXIV_QUERY'))
    parser.add_argument('--smtp_server', type=str, help='SMTP server',default=os.environ.get('SMTP_SERVER'))
    parser.add_argument('--smtp_port', type=int, help='SMTP port',default=os.environ.get('SMTP_PORT'))
    parser.add_argument('--sender', type=str, help='Sender email address',default=os.environ.get('SENDER'))
    parser.add_argument('--receiver', type=str, help='Receiver email address',default=os.environ.get('RECEIVER'))
    parser.add_argument('--password', type=str, help='Sender email password',default=os.environ.get('SENDER_PASSWORD'))
    args = parser.parse_args()
    assert args.zotero_id is not None
    assert args.zotero_key is not None
    assert args.arxiv_query is not None
    today = datetime.datetime.now(tz=datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - datetime.timedelta(days=1)
    print("Retrieving Zotero corpus...")
    corpus = get_zotero_corpus(args.zotero_id, args.zotero_key)
    print("Retrieving Arxiv papers...")
    papers = get_arxiv_paper(args.arxiv_query, yesterday, today)
    if len(papers) == 0:
        print("No new papers found.")
        exit(0)
    print("Reranking papers...")
    papers = rerank_paper(papers, corpus)
    html = render_email(papers)
    print("Sending email...")
    send_email(args.sender, args.receiver, args.password, args.smtp_server, args.smtp_port, html)
    with open('email.html', 'w') as f:
        f.write(html)