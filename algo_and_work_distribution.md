# Algorithm 

## High Level Plan 
query → filter spatially → Lucene index lookup with docid filter → candidate docs → BM25 scoring → ranked results → rerank based on restaurant-user spatial distance → Return top 2 result with name and address

## Data Preparation

We have geotagged restaurants with couple of attributes and user review.

The fields that we have in our dataset is, id,postal_code,longitude,name,attributes.RestaurantsPriceRange2,state,attributes,attributes.RestaurantsGoodForGroups,review_count,is_open,city,stars,attributes.RestaurantsTakeOut,latitude,business_id,address,attributes.GoodForKids,label,review

we will take only fields of our interest. Get rid of rest of the fields. 
Fields of our interest: 

name, latitude, longtitude, city, price_range, noise_level, outdoor_seating, good_for_groups, valet_parking, romantic, intimate, reservation_needed, stars, take_outs, good_for_kids, label, review, address

Since we are working on NLP space, we can convert this data into pure textual data by denormalizing it ie append the <column:> for each attribute of interest of the restaurant row. But keep the essential columns such as id, name, address, latitude, longtitude, contents. eg

'Rush Inn', '17800 Detroit Ave', 41.48419745, -81.82056826, contents: city: 'Lakewood', price_range: low/medium/high, noise_level:loud, outdoor_seating:true, valet_parking: true, romantic: true, intimate:false, reservation_needed: true, stars: 5, take_outs:true, good_for_kids: false, label: american (traditional), review: So, we stopped here on our way to the Side Quest, which is just up the street. \n\nWe did not know what to expect, but came on a 3$ taco night...\n\nI'm so glad we did:)\n\nMostly, the Rush Inn is a bar-ish place, but there's plenty of back and side seating at booths all through. The place has a dark, rich wood tone, and the patrons were decent folks.\n\nThe tacos were EXCEPTIONAL, and their selection is quite good, with all sorts of stuff I intend to try as soon as possible. I think this place would make a nice casual dinner/lunch stop, and if you need to get beverage, the barkeep and wait staff will keep em coming! \n\nSo, for a quick tasty bite, don't walk slow, RUSH IN TO THE RUSH INN! My boyfriend and I heard about this little place near Rush Inn that offered board games and poutine on Friday. When we arrived, they didn't have food because the chef didn't show up (?) so we ventured to this place a block down. Great vibe inside. A typical bar scene, but had great booze selections and a decently large menu to choose from. I ordered the grilled chicken wrap (smothered in buffalo) and my boyfriend ordered the soft crab sandwich.\n\nBOTH WERE DELICIOUS!\n\nWe are both huge foodies, and consider ourselves pretty in tune with all the good eats in or around Cleveland, and this was a treasure of a find. \n\nWe will definitely be going back! Whoever said this is your typical bar food is nuts...what bar has a stir fried veggie dish, home made mashed potatoes, home made soups, flat bread pizzas, peroghes and fresh veggies??  \nThe place is outstanding.  The menu is huge and varied, something for everyone for sure.  6.00 burger night on Wednesdays!  Not to mention, the staff is very accommodating and friendly. Plus the music they play is great.  A great local bar that will serve you really good food....not just bar food, but REALLY good food! Continuous consistency, party of 12 adults/kids. Best wings in Lakewood, this visit tasty bbq and zesty teriyaki. Also generous sides of potato skins and mozzarella sticks. Others in party raved about the burgers, potato pancakes and "really good" fries. Timely service for a busy Friday night. Good noise level so kids are never an issue whether with you or at another booth. Friendly staff this night and always. Seafood and steak dishes always satisfying from previous visits, not what you\'d expect from a "bar food" spot. Keep it up! Second time at Rush Inn and we had great food and service both times! The atmoshere is what you would expect, nothing fancy but clean and comfortable. The fish sandwich was one of the best I've ever had! So well cooked with a unique tartar sauce and super fresh bun. The food came out really fast too and our waitress checked on us often but not in the annoying way :)

note: 
- some data engineering needed to prepare the above format. eg. attributes.RestaurantsPriceRange2 gives value 1/2/3 and we need to convert it to low/mediaum/high. Some other attributes need to be extracted from the attributes map. 
- we will prepare a json document with contents having the actual description of the restaurant because pyserini lucene indexes contents field by default.
- we prepare one jsonl file having one json doc per line for lucene to index. 
- id could be the business_id field


so we have 6 cols. id, name, address, lat, lon and contents (all attributes smashed into one col).

we prepare a json document using these 6 fields. These documents (the contents field) gets indexed by Lucene while index can also retrieve the original doc. 

## Indexing (textual and spatial)

- prepare Lucene index for restaurant id to restaurant attributes for later querying. 
- prepare spatial index ie rtree for restaurant id to lat/lon for later querying. 

## Query

- when user enters query, we first query spatial index (rtree) to find restaurant ids within 25 mile radius. Assume user gives restuarants of his choice and his lat/lon (curent position). Returns set of docid within that spatial scope. 
- set these docids as a docid filter while doing lucene search.  
- search with bm25 ranking function to find the best 5 fits according to user query as a ranked list

from pyserini.pyclass import autoclass

def search_with_docid_filter(searcher, query_str, allowed_docids: set, top_k=10):
    BooleanQuery = autoclass('org.apache.lucene.search.BooleanQuery$Builder')
    TermInSetQuery = autoclass('org.apache.lucene.search.TermInSetQuery')
    BooleanClause = autoclass('org.apache.lucene.search.BooleanClause')
    BytesRef = autoclass('org.apache.lucene.util.BytesRef')

    # Build the docid filter
    bytes_list = [BytesRef(docid.encode()) for docid in allowed_docids]
    docid_filter = TermInSetQuery("id", bytes_list)

    # BM25 query
    bm25_query = searcher.object.buildQuery(query_str)

    builder = BooleanQuery()
    builder.add(bm25_query, BooleanClause.Occur.valueOf("MUST"))
    builder.add(docid_filter, BooleanClause.Occur.valueOf("FILTER"))

    hits = searcher.object.search(builder.build(), top_k)
    return [(hit.docid, hit.score) for hit in hits]


- now we define a ranking function that will modify the rank of the restaurant based on distance from user's current location
- Recommend top 2 restaurants to the user. Give the name and address of the doc by parsing the json doc. 


## Evaluation Data Preparation

Time to prepare evaluation dataset 

- Draft 25 (could be 10) realistic spatio textual queries (user needs to give intent and current location) and use LLM to get top 5 recommendations for each query given this dataset. Prompt LLM to calculate distance based on user's current position and lat/lon of the restuarant. LLM will do a good job at spatial decay, I guess. 
- Manually rank top 5 responses from LLM for each query (rank 1 to 5). Prepare a csv with query id, restaurant id, rank


## Evaluation

Now time to evaluate whether our result is good or not. 

- Take the evaluation dataset csv
- Make those exact spatio textual query prepared before using our search mechanism implemented. 
- Compute MAP, NDCG@k


# Team Work Divide

## Swarvanu
- prepare initial data
- implement rtree spatial indexing
- define ranking function which does reranking of bm25 retreived docuemnts based on spatial distance decay
- Overall direction

## Sumon
- Prepare BM25 Index of the data 
- Write method for querying documents based on bm25 index

## Taeyang
- Write the end to end query mechanism to do spatially filtering followed by BM25 filtering and then reranking the filtered document based on spatial decay funciton designed by Swarvanu 

## Isaac
- Evaluation dataset preparation
- Evaluation

## Everyone Together
- Do fine tuning of the algorithm
- fix issues
- prepare report 

