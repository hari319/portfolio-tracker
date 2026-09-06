## This file is Deprecated and want be use anymore ##


User wanted to create a new feature which is Portfolio Tracker. We can create that in new tab.

- Here challenge is in  Portfolio Tracker tab we will track three Portfolio: Bapa, Madi, Loan this called Portfolio name.

- Every Portfolio will be like a table but separate for each. I am not sure it can be table only but this is just a idea, provide me if anything new we can have it. Col but that will be Scheme,	Invest Date,	Current Date,	Y (year),	M (month),	Q (Quality),	Avg (Average price),	LTP(Last trade pride), Invested amount, 	Buy Charge,	Sell Charge,	Current Total,	Earned, 	Loss,	Annual Return,	Total Return,	Person (Only for loan Portfolio),	Remarks. 
- Row of table will be a tricky way to show:
    - It can be a stock is only bought once, but there can be stock which can be bought many time at different price.
    - If it one time show in a single row but if bought multiple time, then it should show only single row of all total price with Average price but for multiple there should like +/ collapse which show multiple item.
    - On base of Invest Date,	Current Date there will calculation of Y (year),	M (month)
    - On base of Avg (Average price),	LTP(Last trade pride), Invested amount there will be calculation Buy Charge and	Sell Charge price and even Current Total,	Earned, 	Loss,	Annual Return,	Total Return. 
    - For loan there is flied Person which can be Madi or Bapa as value to be selected any one, which can be later use in tracker tab. 
    - There can be also possible that a row was accidentally add but that stock is no more need and it did not also should goto sel stock so there should a possibly to delete that row 
    
- To add a new row, there should be a way, where user will only provide current date, Q, Avg, Remarks. Rest will be calculated based on that.
    - To add user will provide stock Ticker you will fetch stock name. It can also happen some STock name want be able to fetch that unique case only, for that user value will be accepted but user should confirm it. 

- Whenever user wanted to sell he will edit LTP and current date and rest will be calculated self and sell stock will be transfer to different place where same format will be shown but all stock will be listed of sold only of there portfolio only.

- In bought and sold table in end there will be shown total invested amount of all stock,  current total of all stock, earned, loss total and even profit invested amount of all stock - current total of all stock.

- For each stock i also wanted to have a text flied for bought reason, sold reason, Mistake/Learned. This will be only shown when user wanted to see kind of click button and open some place.
    - Later for a feature user wanted to list somewhere all Mistake/Learned at one place to avoidT or learn from it. 

- For each Portfolio, there will list of dividend got, in that there will be stock Symbol, value, date. which will be shown for each Portfolio separately 

- Apart to Portfolio there will be showing a below item there be some fixed value some calculated value
    Current Stock & ETF Invest	5,213,974.77 (Value Fixed)
    Current MF Invest	₹1,300,000 (Value Fixed)
    Current MF Redeem	₹450,000 (Value Fixed)
    Total 	6,963,974.77 (Total of Current Stock & ETF Invest, Current MF Invest, Current MF Redeem )
        
        
    Loan Amount	₹6,530,152.87 (Value Fixed) 
    Reamining Invest From Loan	-₹433,821.90 (Total - Loan Amount)
    Stock Proift 	586,778.17 (loan earned - Loan loss)
    Dividend	1,093.00 (Total  of Dividend amount)
    Current MF Reddem + Profit	₹474,623 (Value Fixed) 
    Current Remaining	₹628,672.53 (Total of Reamining Invest From Loan, Stock Proift,Dividend,Current MF Reddem + Profit) 


- Currently we for tracker tab we add a new row manually after above implementing, Madi table will be get ticker from table of Madi portfolio and there will be some from loan portfolio which is only for Madi which can be identify by Person col and fetch the rest need value, same goes for Bapa portfolio. 
    -A item from tracker will be only removed if stock is sold from main portfolio.

- After above feature is implemented user has a idea to make analysis for buy or sell a stock on based of current/previous days data based on screener tab which we have saved. Where User can provide for buying a stock name and do math on based of data and do a recommendation if its good price/time to buy or not and same goes for selling. BUt mention somewhere this is just technical calculation, fundamental / event / news can vary the decision. l

- After above feature is implemented, User has a idea in tracker tab, where all company in portfolio will be available as well as the Average buy price also, User wanted a new column in tracker called Avg which which will show avg of buy stock price which will be before current price column. DOwn to Avg user wanted to make a calculation but he is not sure how to do it. His basic idea is to make watch on base of Avg buy price and current price, this calculation will help user to identity which is not running in his favour and need to to be exist as the loss can be much after that point it is kind of risk management calculation. With which user will see kind of percentages will red and exist signal may be. For Avg price in user favour we dont show  anything or just percentage in green may be. 