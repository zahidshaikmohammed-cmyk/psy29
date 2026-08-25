from psy29_v4_retrieval import run
if __name__ == '__main__':
    r=run()
    print('PSY29 V4 DATA GATE')
    print(r['status'], r['trading_date'], r['expected'], r['published'], r['fetched'], r['parsed'], r['validated'], r['failed'])
