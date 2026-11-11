"""Category lookup tables.

Data, not logic. Lifted out of `categories.py` because these three tables are
the part that grows -- every new chain, every new MCC, every aggregator
category lands here -- while the resolution order around them stays put.

The ordering of the layers that read these lives in `categories.py`, and the
reasoning for each table is in its own comment.
"""

from __future__ import annotations

from .enums import Category

MCC_TO_CATEGORY: dict[str, Category] = {
    # Dining
    "5812": Category.DINING,  # eating places, restaurants
    "5813": Category.DINING,  # drinking places, bars
    "5814": Category.DINING,  # fast food
    "5811": Category.DINING,  # caterers
    # Grocery vs. the things that are not grocery
    "5411": Category.GROCERY,  # grocery stores, supermarkets
    "5422": Category.GROCERY,  # freezer / meat provisioners
    "5451": Category.GROCERY,  # dairy product stores
    "5462": Category.GROCERY,  # bakeries
    "5499": Category.GROCERY,  # misc food stores, convenience
    "5310": Category.SUPERSTORE,  # discount stores  <- Walmart, Target
    "5300": Category.WHOLESALE_CLUB,  # wholesale clubs <- Costco, Sam's
    "5331": Category.SUPERSTORE,  # variety stores
    # Fuel
    "5541": Category.GAS,  # service stations
    "5542": Category.GAS,  # automated fuel dispensers
    "5552": Category.EV_CHARGING,  # electric vehicle charging
    # Ground transport
    "4111": Category.TRANSIT,  # commuter transport, ferries
    "4112": Category.TRANSIT,  # passenger railways
    "4131": Category.TRANSIT,  # bus lines
    "4121": Category.RIDESHARE,  # taxicabs, limousines, rideshare
    "4789": Category.TRANSIT,  # transportation services, not elsewhere
    # Air
    "4511": Category.AIRFARE,  # airlines, air carriers
    "3000": Category.AIRFARE,  # airline-specific codes begin here
    # Lodging
    "7011": Category.HOTEL,  # hotels, motels, resorts
    "7012": Category.HOTEL,  # timeshares
    "4722": Category.HOTEL,  # travel agencies / tour operators
    # Car rental and cruise
    "7512": Category.CAR_RENTAL,  # automobile rental agency
    "7513": Category.CAR_RENTAL,  # truck rental
    "4411": Category.CRUISE,  # cruise lines
    # Pharmacy
    "5912": Category.DRUGSTORE,  # drug stores, pharmacies
    "5122": Category.DRUGSTORE,  # drugs, proprietaries
    # Digital and entertainment
    "4899": Category.STREAMING,  # cable, satellite, streaming
    "5815": Category.STREAMING,  # digital goods -- media
    "7832": Category.ENTERTAINMENT,  # motion picture theaters
    "7922": Category.ENTERTAINMENT,  # theatrical / ticket agencies
    "7996": Category.ENTERTAINMENT,  # amusement parks
    "7997": Category.ENTERTAINMENT,  # membership clubs
    # Retail
    "5732": Category.ELECTRONICS,  # electronics stores
    "5734": Category.ELECTRONICS,  # computer software stores
    "5942": Category.ONLINE_RETAIL,  # book stores
    "5964": Category.ONLINE_RETAIL,  # direct marketing -- catalog
    "5969": Category.ONLINE_RETAIL,  # direct marketing -- other
    "5311": Category.DEPARTMENT_STORE,  # department stores
    "5651": Category.DEPARTMENT_STORE,  # family clothing
    "5200": Category.HOME_IMPROVEMENT,  # home supply warehouse
    "5211": Category.HOME_IMPROVEMENT,  # lumber, building materials
    "5251": Category.HOME_IMPROVEMENT,  # hardware stores
    # Bills and services
    "4900": Category.UTILITIES,  # utilities -- electric, gas, water
    "4814": Category.UTILITIES,  # telecom
    "4816": Category.UTILITIES,  # computer network services
    "6300": Category.INSURANCE,  # insurance sales / underwriting
    "6513": Category.RENT,  # real estate agents, rent
    "8011": Category.MEDICAL,  # doctors
    "8021": Category.MEDICAL,  # dentists
    "8062": Category.MEDICAL,  # hospitals
}

#: Brands whose MCC routinely surprises people. The value is the MCC the
#: authorization actually carries, which is what the issuer scores.
#: These are the cases that cost a rewards app its credibility, so they are
#: asserted rather than guessed.
KNOWN_MERCHANT_MCC: dict[str, str] = {
    "walmart": "5310",  # discount store, NOT grocery
    "walmart supercenter": "5310",
    "target": "5310",  # discount store, NOT grocery
    "super target": "5310",
    "costco": "5300",  # wholesale club, NOT grocery
    "costco wholesale": "5300",
    "sam's club": "5300",
    "bj's wholesale": "5300",
    "whole foods": "5411",  # genuinely a supermarket
    "trader joe's": "5411",
    "safeway": "5411",
    "kroger": "5411",
    "publix": "5411",
    "aldi": "5411",
    "h-e-b": "5411",
    "wegmans": "5411",
    "7-eleven": "5499",  # convenience, often not the grocery bonus
    "cvs": "5912",
    "walgreens": "5912",
    "rite aid": "5912",
    "starbucks": "5814",
    "dunkin": "5814",
    "chipotle": "5814",
    "din tai fung": "5812",
    "shake shack": "5814",
    "doordash": "5812",  # delivery usually codes as the restaurant category
    "uber eats": "5812",
    "grubhub": "5812",
    "instacart": "5411",  # varies by fulfilment; commonly grocery
    "uber": "4121",
    "lyft": "4121",
    "amazon": "5969",  # direct marketing, NOT a grocery or department store
    "amazon.com": "5969",
    "apple store": "5732",
    "best buy": "5732",
    "home depot": "5200",
    "lowe's": "5200",
    "shell": "5541",
    "chevron": "5541",
    "exxon": "5541",
    "tesla supercharger": "5552",
    "netflix": "4899",
    "spotify": "5815",
    "delta": "4511",
    "united": "4511",
    "american airlines": "4511",
    "marriott": "7011",
    "hilton": "7011",
    "airbnb": "7011",  # commonly lodging, though not always
    "hertz": "7512",
    "enterprise rent-a-car": "7512",
    "subway": "5814",  # the sandwich chain; "subway" also reads as transit
    "panera": "5812",
    "panera bread": "5812",
    "mcdonald's": "5814",
    "burger king": "5814",
    "wendy's": "5814",
    "taco bell": "5814",
    "kfc": "5814",
    "popeyes": "5814",
    "chick-fil-a": "5814",
    "five guys": "5814",
    "in-n-out": "5814",
    "panda express": "5814",
    "sweetgreen": "5814",
    "pizza hut": "5814",
    "domino's": "5814",
    "papa john's": "5814",
    "olive garden": "5812",
    "cheesecake factory": "5812",
    "peet's": "5814",
    "blue bottle": "5814",
    "philz": "5814",
    "sprouts": "5411",
    "sprouts farmers market": "5411",
    "food lion": "5411",
    "giant eagle": "5411",
    "stop & shop": "5411",
    "ralphs": "5411",
    "vons": "5411",
    "albertsons": "5411",
    "winco": "5411",
    "lidl": "5411",
    "amazon fresh": "5411",  # a supermarket, unlike amazon.com
    "whole foods market": "5411",
    "dollar general": "5310",
    "dollar tree": "5310",
    "five below": "5310",
    "ikea": "5712",
    "wayfair": "5712",
    "nordstrom": "5651",
    "macy's": "5651",
    "sephora": "5977",
    "ulta": "5977",
    "lululemon": "5651",
    "nike": "5661",
    "rei": "5941",
    "dick's sporting goods": "5941",
    "southwest": "4511",
    "southwest airlines": "4511",
    "jetblue": "4511",
    "alaska airlines": "4511",
    "spirit airlines": "4511",
    "frontier airlines": "4511",
    "hyatt": "7011",
    "ihg": "7011",
    "holiday inn": "7011",
    "best western": "7011",
    "wyndham": "7011",
    "vrbo": "7011",
    "booking.com": "4722",
    "expedia": "4722",
    "avis": "7512",
    "budget rent a car": "7512",
    "national car rental": "7512",
    "bart": "4111",
    "caltrain": "4111",
    "mta": "4111",
    "amtrak": "4112",
    "trader joes": "5411",  # as it sometimes posts, without the apostrophe
}


#: Words that suggest what a shop *is* when its name is not in the map.
#:
#: This layer exists because no list of merchants is ever finished. "Osteria
#: Mozza" is a restaurant to any reader and was being priced at the base rate
#: because it is not a chain. A guess from the name beats a silent default to
#: OTHER -- but only while it is labelled a guess, which is why these resolve
#: with an `inferred:` provenance that the UI and the advisor both surface.
#:
#: Kept deliberately conservative. A word earns a place here only if it rarely
#: appears in a shop of some other kind; "market" is absent because a flea
#: market, a stock-trading app and a corner shop all claim it.
KEYWORD_CATEGORY: dict[str, Category] = {
    # Places you eat
    "restaurant": Category.DINING,
    "ristorante": Category.DINING,
    "osteria": Category.DINING,
    "trattoria": Category.DINING,
    "pizzeria": Category.DINING,
    "pizza": Category.DINING,
    "taqueria": Category.DINING,
    "cantina": Category.DINING,
    "brasserie": Category.DINING,
    "bistro": Category.DINING,
    "cafe": Category.DINING,
    "caffe": Category.DINING,
    "café": Category.DINING,
    "coffee": Category.DINING,
    "espresso": Category.DINING,
    "roasters": Category.DINING,
    "teahouse": Category.DINING,
    "diner": Category.DINING,
    "grill": Category.DINING,
    "grille": Category.DINING,
    "steakhouse": Category.DINING,
    "bbq": Category.DINING,
    "barbecue": Category.DINING,
    "sushi": Category.DINING,
    "ramen": Category.DINING,
    "noodle": Category.DINING,
    "dumpling": Category.DINING,
    "kitchen": Category.DINING,
    "eatery": Category.DINING,
    "tavern": Category.DINING,
    "brewery": Category.DINING,
    "brewhouse": Category.DINING,
    "pub": Category.DINING,
    "bakery": Category.DINING,
    "patisserie": Category.DINING,
    "creamery": Category.DINING,
    "gelato": Category.DINING,
    "deli": Category.DINING,
    "delicatessen": Category.DINING,
    "buffet": Category.DINING,
    # Food shops. "grocery" and "supermarket" are unambiguous; "market" is not.
    "grocery": Category.GROCERY,
    "groceries": Category.GROCERY,
    "supermarket": Category.GROCERY,
    "supermercado": Category.GROCERY,
    "greengrocer": Category.GROCERY,
    "butcher": Category.GROCERY,
    "fishmonger": Category.GROCERY,
    # Fuel
    "fuel": Category.GAS,
    "petrol": Category.GAS,
    "gasoline": Category.GAS,
    "truckstop": Category.GAS,
    # Staying somewhere
    "hotel": Category.HOTEL,
    "hotels": Category.HOTEL,
    "motel": Category.HOTEL,
    "inn": Category.HOTEL,
    "resort": Category.HOTEL,
    "hostel": Category.HOTEL,
    "suites": Category.HOTEL,
    # Getting there
    "airlines": Category.AIRFARE,
    "airways": Category.AIRFARE,
    "airline": Category.AIRFARE,
    "aviation": Category.AIRFARE,
    "taxi": Category.TRANSIT,
    "cab": Category.TRANSIT,
    "tramway": Category.TRANSIT,
    "railways": Category.TRANSIT,
    "railroad": Category.TRANSIT,
    "transit": Category.TRANSIT,
    "parking": Category.TRANSIT,
    # Health
    "pharmacy": Category.DRUGSTORE,
    "chemist": Category.DRUGSTORE,
    "drugstore": Category.DRUGSTORE,
    "apothecary": Category.DRUGSTORE,
}

#: Tried and rejected, so they are not helpfully re-added: "lodge" (Lodge Cast
#: Iron sells cookware), "metro" (Metro by T-Mobile is a phone carrier),
#: "market" (a flea market is not a supermarket) and "subway" (the sandwich
#: chain outnumbers the railway, and it is in the merchant map instead). Each
#: produced a confidently wrong category on a real merchant name.


#: Plaid's detailed categories, mapped to ours where the match is genuine.
#:
#: The *primary* category is useless for this purpose and that is worth being
#: explicit about: FOOD_AND_DRINK spans both groceries and restaurants, which
#: are different card categories -- Blue Cash Preferred pays 6% on one and 3%
#: on the other. Mapping the primary would mis-price every grocery run. The
#: detailed category splits exactly where the card rules split.
#:
#: Two kinds of OTHER, and the difference is user-visible. A detailed category
#: absent from this table means we do not know what the shop is. One mapped
#: explicitly to OTHER means we know exactly what it is and no card in the
#: corpus pays a bonus for it -- a gym, a bike shop, a gift shop. The second is
#: not a failure to classify, so the row does not say "shop type unknown", and
#: a flat-rate card legitimately winning there is correct advice rather than a
#: gap.
PLAID_DETAILED_CATEGORY: dict[str, Category] = {
    # Eating out, in all its forms
    "FOOD_AND_DRINK_RESTAURANT": Category.DINING,
    "FOOD_AND_DRINK_FAST_FOOD": Category.DINING,
    "FOOD_AND_DRINK_COFFEE": Category.DINING,
    "FOOD_AND_DRINK_BEER_WINE_AND_LIQUOR": Category.DINING,
    "FOOD_AND_DRINK_VENDING_MACHINES": Category.DINING,
    "FOOD_AND_DRINK_OTHER_FOOD_AND_DRINK": Category.DINING,
    # The split the primary category cannot make
    "FOOD_AND_DRINK_GROCERIES": Category.GROCERY,
    # Getting about
    "TRANSPORTATION_GAS": Category.GAS,
    "TRANSPORTATION_TAXIS_AND_RIDE_SHARES": Category.RIDESHARE,
    "TRANSPORTATION_PUBLIC_TRANSIT": Category.TRANSIT,
    "TRANSPORTATION_PARKING": Category.TRANSIT,
    "TRANSPORTATION_TOLLS": Category.TRANSIT,
    # Travel
    "TRAVEL_FLIGHTS": Category.AIRFARE,
    "TRAVEL_LODGING": Category.HOTEL,
    "TRAVEL_RENTAL_CARS": Category.CAR_RENTAL,
    "TRAVEL_PUBLIC_TRANSIT": Category.TRANSIT,
    # Shops
    "GENERAL_MERCHANDISE_SUPERSTORES": Category.SUPERSTORE,
    "GENERAL_MERCHANDISE_ONLINE_MARKETPLACES": Category.ONLINE_RETAIL,
    "GENERAL_MERCHANDISE_ELECTRONICS": Category.ELECTRONICS,
    "GENERAL_MERCHANDISE_DEPARTMENT_STORES": Category.DEPARTMENT_STORE,
    "HOME_IMPROVEMENT_HARDWARE": Category.HOME_IMPROVEMENT,
    # Bills and health
    "MEDICAL_PHARMACIES_AND_SUPPLEMENTS": Category.DRUGSTORE,
    "RENT_AND_UTILITIES_INTERNET_AND_CABLE": Category.UTILITIES,
    "RENT_AND_UTILITIES_GAS_AND_ELECTRICITY": Category.UTILITIES,
    "RENT_AND_UTILITIES_WATER": Category.UTILITIES,
    "RENT_AND_UTILITIES_TELEPHONE": Category.UTILITIES,
    "RENT_AND_UTILITIES_RENT": Category.RENT,
    "ENTERTAINMENT_TV_AND_MOVIES": Category.STREAMING,
    "ENTERTAINMENT_MUSIC_AND_AUDIO": Category.STREAMING,
    # Known, and knowingly unbonused. Mapped rather than omitted so the row
    # reads as a classification instead of a shrug.
    "TRANSPORTATION_BIKES_AND_SCOOTERS": Category.OTHER,
    "PERSONAL_CARE_GYMS_AND_FITNESS_CENTERS": Category.OTHER,
    "PERSONAL_CARE_HAIR_AND_BEAUTY": Category.OTHER,
    "PERSONAL_CARE_LAUNDRY_AND_DRY_CLEANING": Category.OTHER,
    "GENERAL_MERCHANDISE_GIFTS_AND_NOVELTIES": Category.OTHER,
    "GENERAL_MERCHANDISE_CONVENIENCE_STORES": Category.OTHER,
    "GENERAL_MERCHANDISE_OFFICE_SUPPLIES": Category.OTHER,
    "GENERAL_MERCHANDISE_PET_SUPPLIES": Category.OTHER,
    "GENERAL_MERCHANDISE_CLOTHING_AND_ACCESSORIES": Category.OTHER,
    "GENERAL_MERCHANDISE_SPORTING_GOODS": Category.OTHER,
    "HOME_IMPROVEMENT_FURNITURE": Category.OTHER,
    "ENTERTAINMENT_SPORTING_EVENTS_AMUSEMENT_PARKS_AND_MUSEUMS": Category.ENTERTAINMENT,
}
