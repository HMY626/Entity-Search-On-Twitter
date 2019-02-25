import cPickle
import os
import twitter
import json
import sys
import time
import networkx as nx
import matplotlib.pyplot as plt

from functools import partial
from sys import maxint
from urllib2 import URLError
from httplib import BadStatusLine
from collections import Counter
from prettytable import PrettyTable

# ----------------------------------
# 作者: santu                       | 
# 注意: 需要引用请标明出处             |
# ----------------------------------

# 以下是我查询的热门话题, 但是Twitter对于api请求次数会做出限制，如果发现有15分钟以后再尝试的提示，那就一个一个搜。
# screen_names = ['ianozsvald', 'annotateio', 'morconsulting',
#                 'brouberol', 'markpriestley', 'steeevem',
#                 'lovedaybrooke', 'jameshaycock', 'localben']


# 先去Twitter开发者申请一个账号，申请开发者权限，并且补充OAuth_Token
def oauth_login():

    CONSUMER_KEY = ''
    CONSUMER_SECRET = ''
    OAUTH_TOKEN = ''
    OAUTH_TOKEN_SECRET = ''

    auth = twitter.oauth.OAuth(OAUTH_TOKEN, OAUTH_TOKEN_SECRET,
                               CONSUMER_KEY, CONSUMER_SECRET)

    twitter_api = twitter.Twitter(auth=auth)
    return twitter_api


# 获取topic的关注者与好友
def get_friends_followers_ids(twitter_api, screen_name=None, user_id=None,
                              friends_limit=maxint, followers_limit=maxint):

    # Must have either screen_name or user_id (logical xor)
    assert (screen_name != None) != (user_id != None), \
    "Must have screen_name or user_id, but not both"

    # See https://dev.twitter.com/docs/api/1.1/get/friends/ids and
    # https://dev.twitter.com/docs/api/1.1/get/followers/ids for details
    # on API parameters

    get_friends_ids = partial(make_twitter_request, twitter_api.friends.ids,
                              count=5000)
    get_followers_ids = partial(make_twitter_request, twitter_api.followers.ids,
                                count=5000)

    friends_ids, followers_ids = [], []

    for twitter_api_func, limit, ids, label in [
                    [get_friends_ids, friends_limit, friends_ids, "friends"],
                    [get_followers_ids, followers_limit, followers_ids, "followers"]
                ]:

        if limit == 0: continue

        cursor = -1
        while cursor != 0:

            # Use make_twitter_request via the partially bound callable...
            if screen_name:
                response = twitter_api_func(screen_name=screen_name, cursor=cursor)
            else: # user_id
                response = twitter_api_func(user_id=user_id, cursor=cursor)

            if response is not None:
                ids += response['ids']
                cursor = response['next_cursor']

            print >> sys.stderr, 'Fetched {0} total {1} ids for {2}'.format(len(ids),
                                                    label, (user_id or screen_name))

            # XXX: You may want to store data during each iteration to provide an
            # an additional layer of protection from exceptional circumstances

            if len(ids) >= limit or response is None:
                break

    # Do something useful with the IDs, like store them to disk...
    return friends_ids[:friends_limit], followers_ids[:followers_limit]


# 创建Twitter请求
def make_twitter_request(twitter_api_func, max_errors=10, *args, **kw):

    # A nested helper function that handles common HTTPErrors. Return an updated
    # value for wait_period if the problem is a 500 level error. Block until the
    # rate limit is reset if it's a rate limiting issue (429 error). Returns None
    # for 401 and 404 errors, which requires special handling by the caller.
    def handle_twitter_http_error(e, wait_period=2, sleep_when_rate_limited=True):

        if wait_period > 3600: # Seconds
            print >> sys.stderr, 'Too many retries. Quitting.'
            raise e

        # See https://dev.twitter.com/docs/error-codes-responses for common codes

        if e.e.code == 401:
            print >> sys.stderr, 'Encountered 401 Error (Not Authorized)'
            return None
        elif e.e.code == 404:
            print >> sys.stderr, 'Encountered 404 Error (Not Found)'
            return None
        elif e.e.code == 429:
            print >> sys.stderr, 'Encountered 429 Error (Rate Limit Exceeded)'
            if sleep_when_rate_limited:
                print >> sys.stderr, "Retrying in 15 minutes...ZzZ..."
                sys.stderr.flush()
                time.sleep(60*15 + 5)
                print >> sys.stderr, '...ZzZ...Awake now and trying again.'
                return 2
            else:
                raise e # Caller must handle the rate limiting issue
        elif e.e.code in (500, 502, 503, 504):
            print >> sys.stderr, 'Encountered %i Error. Retrying in %i seconds' % \
                (e.e.code, wait_period)
            time.sleep(wait_period)
            wait_period *= 1.5
            return wait_period
        else:
            raise e

    # End of nested helper function

    wait_period = 2
    error_count = 0

    while True:
        try:
            return twitter_api_func(*args, **kw)
        except twitter.api.TwitterHTTPError, e:
            error_count = 0
            wait_period = handle_twitter_http_error(e, wait_period)
            if wait_period is None:
                return
        except URLError, e:
            error_count += 1
            time.sleep(wait_period)
            wait_period *= 1.5
            print >> sys.stderr, "URLError encountered. Continuing."
            if error_count > max_errors:
                print >> sys.stderr, "Too many consecutive errors...bailing out."
                raise
        except BadStatusLine, e:
            error_count += 1
            time.sleep(wait_period)
            wait_period *= 1.5
            print >> sys.stderr, "BadStatusLine encountered. Continuing."
            if error_count > max_errors:
                print >> sys.stderr, "Too many consecutive errors...bailing out."
                raise


# 合并数据集
def combine_dataset(DATA_DIR):
	all_screens = {}
	with open("all_screens.json", "w") as f:
    	for file in os.listdir(DATA_DIR):
        	file_name = DATA_DIR + "/" + file
        	with open(file_name, "r") as fp:
            	all_screens[file.split("_")[0]] = json.load(fp)
    	all_scr = json.dumps(all_screens, indent=4)
    	f.write(all_scr)
    return os.path.abspath("all_screens.json")


# 获取数据
def get_data(screen_names):
    print "Downloading friends and followers for:", screen_names
    for screen_name in screen_names:
        #fr_filename, fo_filename = get_filenames(screen_name)
        #print "Checking for:", fr_filename, fo_filename
        #if not os.path.exists(fr_filename):
        print "Getting friends and followers for", screen_name
        fr, fo = get_friends_followers_ids(twitter_api,
                                           screen_name=screen_name,
                                           friends_limit=2,
                                           followers_limit=100)

        friend_ids = json.dumps(fr, indent=4)
        with open('%s_fr.json' % (screen_name), 'w') as f:
            f.write(friend_ids)
        follower_ids = json.dumps(fo, indent=4)
        with open('%s_fo.json' % (screen_name), 'w') as f:
            f.write(follower_ids)
    print "Finished!"    


# 绘制社交网络拓扑图
def draw_network(dataset_loc):
    with open(dataset_loc, "r") as f:
        data = json.load(f)

    # 构建图
    G = nx.Graph()
    for screen_name, followers in data.items():
        G.add_node(screen_name)
        G.add_nodes_from(followers)
        for follower in followers:
            G.add_edge(follower, screen_name)

    # 设置最大跟随数
    MAX_WITH_0_FOLLOWERS = 40
    for screen_name, followers in data.items():
        nbr_with_no_followers = 0
        for follower in followers:
            edges_of_connected_node = G.edges(follower)
            if len(edges_of_connected_node) == 1:
                if nbr_with_no_followers == MAX_WITH_0_FOLLOWERS:
                    G.remove_node(follower)
                else:
                    nbr_with_no_followers += 1
        print "Capping:", screen_name, nbr_with_no_followers

    # 标注主要结点
    labels = {}
    for node in G.nodes():
        labels[node] = ""
        if len(G.edges(node)) > 10:
            labels[node] = node

    nx.draw_networkx(G, with_labels=True, alpha=0.2, labels=labels, font_size=10, font_family='sans-serif')

    plt.axis("off")
    plt.title("Twitter social network topology")
    plt.rcParams['figure.figsize'] = (8.0, 4.0) # 设置figure_size尺寸
    plt.rcParams['image.interpolation'] = 'nearest' # 设置 interpolation style
    plt.rcParams['savefig.dpi'] = 300 #图片像素
    plt.rcParams['figure.dpi'] = 300 #分辨率
    plt.savefig("Social network topology.png")
    plt.show()


# 搜索流行话题
def twitter_trends(twitter_api, woe_id):
    '''http://developer.yahoo.com/geo/geoplanet/ for details on Yahoo! Where On Earth ID'''
    return twitter_api.trends.place(_id=woe_id)


# 取热榜话题交集
def union(placeA_trends, placeB_trends):
    placeA_trends_set = set([trend['name'] for trend in placeA_trends[0]['trends']])
    placeB_trends_set = set([trend['name'] for trend in placeB_trends[0]['trends']])
    common_trends = placeA_trends_set & placeB_trends_set
    return list(common_trends)



# 查询推文
def twitter_search(twitter_api, q, max_results=200, **kw):

    search_results = twitter_api.search.tweets(q=q, count=100, **kw)
    statuses = search_results['statuses']

    max_results = min(1000, max_results)

    for _ in range(10): # 10*100 = 1000
        try:
            next_results = search_results['search_metadata']['next_results']
        except KeyError, e: # No more results when next_results doesn't exist
            break

        # Create a dictionary from next_results, which has the following form:
        # ?max_id=313519052523986943&q=NCAA&include_entities=1
        kwargs = dict([ kv.split('=')
                        for kv in next_results[1:].split("&") ])

        search_results = twitter_api.search.tweets(**kwargs)
        statuses += search_results['statuses']

        if len(statuses) > max_results:
            break

    # 存入json
    data = json.dumps(statuses, indent=4)
    with open('%s_statuses.json' % (q) , 'w') as f:
        f.write(data)

    return statuses


# 提取推文实体
def extract_tweet_entities(statuses):

    if len(statuses) == 0:
        return [], [], [], [], []

    screen_names = [ user_mention['screen_name']
                         for status in statuses
                            for user_mention in status['entities']['user_mentions'] ]

    hashtags = [ hashtag['text']
                     for status in statuses
                        for hashtag in status['entities']['hashtags'] ]

    urls = [ url['expanded_url']
                     for status in statuses
                        for url in status['entities']['urls'] ]

    symbols = [ symbol['text']
                   for status in statuses
                       for symbol in status['entities']['symbols'] ]

    # 在有的推文中没有media
    if status['entities'].has_key('media'):
        media = [ media['url']
                         for status in statuses
                            for media in status['entities']['media'] ]
    else:
        media = []

    return screen_names, hashtags, urls, media, symbols


# 查找最流行的推文
def get_common_tweet_entities(statuses, entity_threshold=3):

    # Create a flat list of all tweet entities
    tweet_entities = [  e
                        for status in statuses
                            for entity_type in extract_tweet_entities([status])
                                for e in entity_type
                     ]

    c = Counter(tweet_entities).most_common()

    # Compute frequencies
    return [ (k,v)
             for (k,v) in c
                 if v >= entity_threshold
           ]


# 绘制频率分析表
def draw_table(search_results):
    common_entities = get_common_tweet_entities(search_results)
    # Use PrettyTable to create a nice tabular display
    pt = PrettyTable(field_names=['Entity', 'Count'])
    [ pt.add_row(kv) for kv in common_entities ]
    pt.align['Entity'], pt.align['Count'] = 'l', 'r' # Set column alignment
    print pt


# 提取用户个人信息
def get_user_profile(twitter_api, screen_names=None, user_ids=None):

    # Must have either screen_name or user_id (logical xor)
    assert (screen_names != None) != (user_ids != None), \
    "Must have screen_names or user_ids, but not both"

    items_to_info = {}

    items = screen_names or user_ids

    while len(items) > 0:

        # Process 100 items at a time per the API specifications for /users/lookup.
        # See https://dev.twitter.com/docs/api/1.1/get/users/lookup for details.

        items_str = ','.join([str(item) for item in items[:100]])
        items = items[100:]

        if screen_names:
            response = make_twitter_request(twitter_api.users.lookup,
                                            screen_name=items_str)
        else: # user_ids
            response = make_twitter_request(twitter_api.users.lookup,
                                            user_id=items_str)

        for user_info in response:
            if screen_names:
                items_to_info[user_info['screen_name']] = user_info
            else: # user_ids
                items_to_info[user_info['id']] = user_info

    return items_to_info


# 分析推文内容
def analyze_tweet_content(statuses):

    if len(statuses) == 0:
        print "No statuses to analyze"
        return

    # A nested helper function for computing lexical diversity
    def lexical_diversity(tokens):
        return 1.0*len(set(tokens))/len(tokens)

    # A nested helper function for computing the average number of words per tweet
    def average_words(statuses):
        total_words = sum([ len(s.split()) for s in statuses ])
        return 1.0*total_words/len(statuses)

    status_texts = [ status['text'] for status in statuses ]
    screen_names, hashtags, urls, media, _ = extract_tweet_entities(statuses)

    # Compute a collection of all words from all tweets
    words = [ w
          for t in status_texts
              for w in t.split() ]

    print "Lexical diversity (words):", lexical_diversity(words)
    print "Lexical diversity (screen names):", lexical_diversity(screen_names)
    print "Lexical diversity (hashtags):", lexical_diversity(hashtags)
    print "Averge words per tweet:", average_words(status_texts)


# 分析用户收藏推文
def analyze_favorites(twitter_api, screen_name, entity_threshold=2):
    
    # Could fetch more than 200 by walking the cursor as shown in other
    # recipes, but 200 is a good sample to work with.
    favs = twitter_api.favorites.list(screen_name=screen_name, count=200)
    print "Number of favorites:", len(favs)
    
    # Figure out what some of the common entities are, if any, in the content
    
    common_entities = get_common_tweet_entities(favs, 
                                                entity_threshold=entity_threshold)
    
    # Use PrettyTable to create a nice tabular display
    
    pt = PrettyTable(field_names=['Entity', 'Count']) 
    [ pt.add_row(kv) for kv in common_entities ]
    pt.align['Entity'], pt.align['Count'] = 'l', 'r' # Set column alignment
    
    print
    print "Common entities in favorites..."
    print pt
        
    # Print out some other stats
    print
    print "Some statistics about the content of the favorities..."
    print
    analyze_tweet_content(favs)
    
    # Could also start analyzing link content or summarized link content, and more.


if __name__ == "__main__":
    # 认证登陆
    twitter_api = oauth_login()
    # 查找美国国内热榜和世界热榜并取交集
    WORLD_WOE_ID = 1
    world_trends = twitter_trends(twitter_api, WORLD_WOE_ID)
    US_WOE_ID = 23424977
    us_trends = twitter_trends(twitter_api, US_WOE_ID)
    screen_names = union(world_trends, us_trends)
    print screen_names
    
    # 获取数据
    get_data(screen_names)
    # 将数据集合并成字典
    DATA_DIR = r'/root/Twitter/extend_application/test_pickle/data'
    dataset_loc = combine_dataset(DATA_DIR)
    # 绘制社交网络拓扑图
    #draw_network(dataset_loc)
    # 查找重要结点推文
    q = raw_input("需要查询的推文名:")
    search_results = twitter_search(twitter_api, q, max_results=10)
    
    # 打印数据集中的一个列表
    judge = raw_input("是否打印样例(y or n):")
    if judge == "y":
        print "其中一个列表数据样例如下所示:\n"
        print json.dumps(search_results[0], indent=4)
    else:
        pass
    
    # 提取推文实体
    screen_names, hashtags, urls, media, symbols = extract_tweet_entities(search_results)
    judge = raw_input("是否打印实体样例(y or n):")
    if judge == "y":
        print json.dumps(screen_names[0:5], indent=4)
        print json.dumps(hashtags[0:5], indent=4)
        print json.dumps(urls[0:5], indent=4)
        print json.dumps(media[0:5], indent=4)
        print json.dumps(symbols[0:5], indent=4)
    else:
        pass
    
    # 查询最流行的推文
    common_entities = get_common_tweet_entities(search_results)
    print "最热门的推文实体"
    print common_entities
    # 绘制词频表
    draw_table(search_results)
    # 分析推文内容
    analyze_tweet_content(search_results)
    # 提取用户个人信息
    print get_user_profile(twitter_api, screen_names=screen_names)
    # 分析用户收藏推文
    analyze_favorites(twitter_api, q)
