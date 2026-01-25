#webscraping using R

library(rvest)
library(stringr)  # Added for string manipulation functions
#library(dplyr)

library('lubridate')
library('dplyr')
library('readr')
library('flextable')
library(caret)
#library('htmlwidgets')
#library('dygraphs')
#library('webshot')
# Reading the HTML code from the website
#webpage = read_html("https://www.screener.in/company/ADANIENT/")

# Using CSS selectors to scrape the heading section
#output<-webpage %>% html_nodes('div') %>% lapply(html_nodes, 'li') %>% lapply(html_text, trim = TRUE) 
#output[[51]]

#output<-webpage %>% html_table()

#output[[1]]%>%data.frame()

#paragraph = html_nodes(webpage, 'p')

#get_screener_company_data(symbol)

#symbol <- "GAIL"

#https://www.screener.in/screens/325075/all-latest-quarterly-results/
get_screener_company_data <- function(symbol)
{
  
  url <- paste0("https://www.screener.in/company/", symbol, "/")
  url = url(url, "rb")
  webpage<- read_html(url)
  output<-webpage %>% html_nodes('div') %>% lapply(html_nodes, 'li') %>% lapply(html_text, trim = TRUE) 
  dt<- output[[57]]
  v<-str_replace_all(dt, "[\n]", "")
  v<-str_replace_all(v, " ", "")
  v<-str_replace_all(v, "\u20B9", "")
  m<-str_locate(v, "[0-9]")
  
  
  v<-as.data.frame(v)
  
  if(ncol(v)>=1){
        
        m<-as.data.frame(m)
        m[is.na(m)]<-0
        #str_split(v[1,1],paste0("^(.{", m[i, "start"]-1, "})(.*)$" ),2, FALSE )
        #gsub(v, pattern = "[0-9]", replacement = "\\1 \\2")
        
        x<-data.frame()
        for(i in c(1:nrow(v)))
        {
          # DEBUG capture of current raw string and locator row
          last_parse_debug <<- list(context="company_data_main", index=i, raw=v[i,1], m_row=m[i,])
          # SAFE PARSE: handle possible NA in m$start to avoid 'missing value where TRUE/FALSE needed'
          if(!is.na(m$start[i]) && m$start[i] > 0)
          {
             p<- gsub(paste0("^(.{", m[i, "start"]-1, "})(.*)$"),
                      paste0("\\1", ":", "\\2"),
                      v[i,c(1)])
            tag<- str_split( p, ":", n=2, simplify=TRUE)[1]
            val<- str_split( p, ":", n=2, simplify=TRUE)[2]
          }
          else
          {
            tag <- v[i,c(1)]
            val <- 0
          }
          
          x<-rbind(x,cbind(tag,val))
        }
        print(x)
        #close.connection(url)
  }
    else{
      url <- paste0("https://www.screener.in/company/", symbol, "/consolidated/")
      url = url(url, "rb")
      webpage<- read_html(url)
      output<-webpage %>% html_nodes('div') %>% lapply(html_nodes, 'li') %>% lapply(html_text, trim = TRUE) 
      dt<- output[[58]]
      v<-str_replace_all(dt, "[\n]", "")
      v<-str_replace_all(v, " ", "")
      v<-str_replace_all(v, "\u20B9", "")
      m<-str_locate(v, "[0-9]")
      
      
      v<-as.data.frame(v)
      m<-as.data.frame(m)
      m[is.na(m)]<-0
      #str_split(v[1,1],paste0("^(.{", m[i, "start"]-1, "})(.*)$" ),2, FALSE )
      #gsub(v, pattern = "[0-9]", replacement = "\\1 \\2")
      
      x<-data.frame()
      for(i in c(1:nrow(v)))
      {
        # DEBUG capture
        last_parse_debug <<- list(context="company_data_fallback", index=i, raw=v[i,1], m_row=m[i,])
        # SAFE PARSE: handle possible NA in m$start
        if(!is.na(m$start[i]) && m$start[i] > 0)
        {
          p<- gsub(paste0("^(.{", m[i, "start"]-1, "})(.*)$"),
                   paste0("\\1", ":", "\\2"),
                   v[i,c(1)])
          tag<- str_split( p, ":", n=2, simplify=TRUE)[1]
          val<- str_split( p, ":", n=2, simplify=TRUE)[2]
        }
        else
        {
          tag <- v[i,c(1)]
          val <- 0
        }
        
        x<-rbind(x,cbind(tag,val))
      }
      print(x)
      #close.connection(url)
      
    }
  get_screener_company_data<-x
  
}


#https://www.screener.in/screens/325075/all-latest-quarterly-results/
get_screener_book_to_trade_data <- function(symbol)
{
  
  url <- paste0("https://www.screener.in/company/", symbol, "/")
  url = url(url, "rb")
  webpage<- read_html(url)
  output<-webpage %>% html_nodes('div') %>% lapply(html_nodes, 'li') %>% lapply(html_text, trim = TRUE) 
  dt<- output[[58]]
  v<-str_replace_all(dt, "[\n]", "")
  v<-str_replace_all(v, " ", "")
  v<-str_replace_all(v, "\u20B9", "")
  m<-str_locate(v, "[0-9]")
  
  
  v<-as.data.frame(v)
  
  if(ncol(v)>=1){
    
    m<-as.data.frame(m)
    m[is.na(m)]<-0
    #str_split(v[1,1],paste0("^(.{", m[i, "start"]-1, "})(.*)$" ),2, FALSE )
    #gsub(v, pattern = "[0-9]", replacement = "\\1 \\2")
    
    x<-data.frame()
    for(i in c(1:nrow(v)))
    {
      # SAFE PARSE: handle possible NA in m$start
      if(!is.na(m$start[i]) && m$start[i] > 0)
      {
        p<- gsub(paste0("^(.{", m[i, "start"]-1, "})(.*)$"),
                 paste0("\\1", ":", "\\2"),
                 v[i,c(1)])
        tag<- str_split( p, ":", n=2, simplify=TRUE)[1]
        val<- str_split( p, ":", n=2, simplify=TRUE)[2]
      }
      else
      {
        tag <- v[i,c(1)]
        val <- 0
      }
      
      x<-rbind(x,cbind(tag,val))
    }
    print(x)
    #close.connection(url)
  }
  else{
    url <- paste0("https://www.screener.in/company/", symbol, "/consolidated/")
    url = url(url, "rb")
    webpage<- read_html(url)
    output<-webpage %>% html_nodes('div') %>% lapply(html_nodes, 'li') %>% lapply(html_text, trim = TRUE) 
    dt<- output[[58]]
    v<-str_replace_all(dt, "[\n]", "")
    v<-str_replace_all(v, " ", "")
    v<-str_replace_all(v, "\u20B9", "")
    m<-str_locate(v, "[0-9]")
    
    
    v<-as.data.frame(v)
    m<-as.data.frame(m)
    m[is.na(m)]<-0
    #str_split(v[1,1],paste0("^(.{", m[i, "start"]-1, "})(.*)$" ),2, FALSE )
    #gsub(v, pattern = "[0-9]", replacement = "\\1 \\2")
    
    x<-data.frame()
    for(i in c(1:nrow(v)))
    {
      # SAFE PARSE: handle possible NA in m$start
      if(!is.na(m$start[i]) && m$start[i] > 0)
      {
        p<- gsub(paste0("^(.{", m[i, "start"]-1, "})(.*)$"),
                 paste0("\\1", ":", "\\2"),
                 v[i,c(1)])
        tag<- str_split( p, ":", n=2, simplify=TRUE)[1]
        val<- str_split( p, ":", n=2, simplify=TRUE)[2]
      }
      else
      {
        tag <- v[i,c(1)]
        val <- 0
      }
      
      x<-rbind(x,cbind(tag,val))
    }
    print(x)
    #close.connection(url)
    
  }
  get_screener_book_to_trade_data<-x
  
}


get_screener_roe_data <- function(symbol)
{
  
  url <- paste0("https://www.screener.in/company/", symbol, "/")
  url = url(url, "rb")
  webpage<- read_html(url)
  output<-webpage %>% html_nodes('div') %>% lapply(html_nodes, 'li') %>% lapply(html_text, trim = TRUE) 
  dt<- output[[58]]
  v<-str_replace_all(dt, "[\n]", "")
  v<-str_replace_all(v, " ", "")
  v<-str_replace_all(v, "\u20B9", "")
  m<-str_locate(v, "[0-9]")
  
  
  v<-as.data.frame(v)
  
  if(ncol(v)>=1){
    
    m<-as.data.frame(m)
    m[is.na(m)]<-0
    #str_split(v[1,1],paste0("^(.{", m[i, "start"]-1, "})(.*)$" ),2, FALSE )
    #gsub(v, pattern = "[0-9]", replacement = "\\1 \\2")
    
    x<-data.frame()
    for(i in c(1:nrow(v)))
    {
      # SAFE PARSE: handle possible NA in m$start
      if(!is.na(m$start[i]) && m$start[i] > 0)
      {
        p<- gsub(paste0("^(.{", m[i, "start"]-1, "})(.*)$"),
                 paste0("\\1", ":", "\\2"),
                 v[i,c(1)])
        tag<- str_split( p, ":", n=2, simplify=TRUE)[1]
        val<- str_split( p, ":", n=2, simplify=TRUE)[2]
      }
      else
      {
        tag <- v[i,c(1)]
        val <- 0
      }
      
      x<-rbind(x,cbind(tag,val))
    }
    print(x)
    #close.connection(url)
  }
  else{
    url <- paste0("https://www.screener.in/company/", symbol, "/consolidated/")
    url = url(url, "rb")
    webpage<- read_html(url)
    output<-webpage %>% html_nodes('div') %>% lapply(html_nodes, 'li') %>% lapply(html_text, trim = TRUE) 
    dt<- output[[58]]
    v<-str_replace_all(dt, "[\n]", "")
    v<-str_replace_all(v, " ", "")
    v<-str_replace_all(v, "\u20B9", "")
    m<-str_locate(v, "[0-9]")
    
    
    v<-as.data.frame(v)
    m<-as.data.frame(m)
    m[is.na(m)]<-0
    #str_split(v[1,1],paste0("^(.{", m[i, "start"]-1, "})(.*)$" ),2, FALSE )
    #gsub(v, pattern = "[0-9]", replacement = "\\1 \\2")
    
    x<-data.frame()
    for(i in c(1:nrow(v)))
    {
      # SAFE PARSE: handle possible NA in m$start
      if(!is.na(m$start[i]) && m$start[i] > 0)
      {
        p<- gsub(paste0("^(.{", m[i, "start"]-1, "})(.*)$"),
                 paste0("\\1", ":", "\\2"),
                 v[i,c(1)])
        tag<- str_split( p, ":", n=2, simplify=TRUE)[1]
        val<- str_split( p, ":", n=2, simplify=TRUE)[2]
      }
      else
      {
        tag <- v[i,c(1)]
        val <- 0
      }
      
      x<-rbind(x,cbind(tag,val))
    }
    print(x)
    #close.connection(url)
    
  }
  get_screener_roe_data<-x
  
}


#symbol <- "512068"
#p<- get_screener_quarterly_results_data(symbol)

get_screener_quarterly_results_data <- function(symbol)
{
  
  url <- paste0("https://www.screener.in/company/", symbol, "/consolidated/")
  url = url(url, "rb")
  webpage<- read_html(url)
  output<-webpage %>% html_table()
  quarterly_results <- output[[1]]%>%data.frame()%>%mutate(across(where(is.character), str_remove_all, pattern = fixed(",")))
  if(ncol(quarterly_results)>1)
  {
    
    
    #colnames(roe)<- c("Years", "roe.cagr")
    colnames(quarterly_results)[1] <- "Items"
    quarterly_results$Items<- str_replace_all(quarterly_results$Items, "[ +]", "")
    
    quarterly_results$Items<-str_replace_all(quarterly_results$Items,"[[:space:]]", "")
    
    quarterly_results <- quarterly_results[c(1:nrow(quarterly_results)-1 ), ]
    
    #close.connection(url)
    Sys.sleep(2)
  }else
  {
    url <- paste0("https://www.screener.in/company/", symbol, "/" )
    url = url(url, "rb")
    webpage<- read_html(url)
    output<-webpage %>% html_table()
    quarterly_results <- output[[1]]%>%data.frame()%>%mutate(across(where(is.character), str_remove_all, pattern = fixed(",")))
    
    #colnames(roe)<- c("Years", "roe.cagr")
    colnames(quarterly_results)[1] <- "Items"
    quarterly_results$Items<- str_replace_all(quarterly_results$Items, "[ +]", "")
    
    quarterly_results$Items<-str_replace_all(quarterly_results$Items,"[[:space:]]", "")
    
    quarterly_results <- quarterly_results[c(1:nrow(quarterly_results)-1 ), ]
    
    #close.connection(url)
    Sys.sleep(2)
    
  }
  get_screener_quarterly_results_data<-quarterly_results
  
}

get_screener_pnl_data <- function(symbol)
{
  
  url <- paste0("https://www.screener.in/company/", symbol,  "/consolidated/")  
  webpage<- read_html(url)
  output<-webpage %>% html_table()
  pnl <- output[[2]]%>%data.frame()%>%data.frame()%>%mutate(across(where(is.character), str_remove_all, pattern = fixed(",")))
  colnames(pnl)[1] <- "Items"
  pnl$Items <- str_replace_all(pnl$Items, "[+]", "")
  pnl$Items <- str_replace_all(pnl$Items, "[[:space:]]", "")
  if(ncol(pnl)==1)
  {
    
    url <- paste0("https://www.screener.in/company/", symbol)
    url = url(url, "rb")
    webpage<- read_html(url)
    output<-webpage %>% html_table()
    pnl <- output[[2]]%>%data.frame()%>%data.frame()%>%mutate(across(where(is.character), str_remove_all, pattern = fixed(",")))
    colnames(pnl)[1] <- "Items"
    pnl$Items <- str_replace_all(pnl$Items, "[+]", "")
    pnl$Items <- str_replace_all(pnl$Items, "[[:space:]]", "")
  }
  ##close.connection(url)
  Sys.sleep(3)
  get_screener_pnl_data<-pnl
  
}

get_screener_comp_sales_growth_data <- function(symbol)
{
  
  url <- paste0("https://www.screener.in/company/", symbol)
  url = url(url, "rb")
  webpage<- read_html(url)
  output<-webpage %>% html_table()
  comp_sales_growth <- output[[3]]%>%data.frame()
  colnames(comp_sales_growth)<- c("Years", "sales.growth")
  #close.connection(url)
  Sys.sleep(3)
  get_screener_comp_sales_growth_data<-comp_sales_growth
  
}


get_screener_comp_profit_growth_data <- function(symbol)
{
  
  url <- paste0("https://www.screener.in/company/", symbol)
  url = url(url, "rb")
  webpage<- read_html(url)
  output<-webpage %>% html_table()
  comp_profit_growth <- output[[4]]%>%data.frame()
  colnames(comp_profit_growth)<- c("Years", "profit.growth")
  #close.connection(url)
  Sys.sleep(3)
  get_screener_comp_profit_growth_data<-comp_profit_growth
  
}


get_screener_comp_spcagr_data <- function(symbol)
{
  
  url <- paste0("https://www.screener.in/company/", symbol, "/consolidated/")
  url = url(url, "rb")
  webpage<- read_html(url)
  output<-webpage %>% html_table()
  spcagr <- output[[5]]%>%data.frame()
  colnames(spcagr)<- c("Years", "stock.price.cagr")
  #close.connection(url)
  Sys.sleep(3)
  get_screener_comp_spcagr_data<-spcagr
  
}

get_screener_comp_roe_data <- function(symbol)
{
  
  url <- paste0("https://www.screener.in/company/", symbol, "/consolidated/")
  url = url(url, "rb")
  webpage<- read_html(url)
  output<-webpage %>% html_table()
  roe <- output[[6]]%>%data.frame()
  colnames(roe)<- c("Years", "roe.cagr")
  #close.connection(url)
  Sys.sleep(3)
  get_screener_comp_roe_data<-roe
  
}


get_screener_balancesheet_data <- function(symbol)
{
  
  url <- paste0("https://www.screener.in/company/", symbol, "/consolidated/")
  
  url = url(url, "rb")
  webpage<- read_html(url)
  output<-webpage %>% html_table()
  balancesheet <- output[[7]]%>%data.frame()%>%mutate(across(where(is.character), str_remove_all, pattern = fixed(",")))
  #colnames(roe)<- c("Years", "roe.cagr")
  colnames(balancesheet)[1] <- "Items"
  balancesheet$Items <- str_replace_all(balancesheet$Items, "[+]", "")
  balancesheet$Items <- str_replace_all(balancesheet$Items, "[[:space:]]", "")
  if(ncol(balancesheet)==1)
  {
    url <- paste0("https://www.screener.in/company/", symbol)
    
    url = url(url, "rb")
    webpage<- read_html(url)
    output<-webpage %>% html_table()
    balancesheet <- output[[7]]%>%data.frame()%>%mutate(across(where(is.character), str_remove_all, pattern = fixed(",")))
    #colnames(roe)<- c("Years", "roe.cagr")
    colnames(balancesheet)[1] <- "Items"
    balancesheet$Items <- str_replace_all(balancesheet$Items, "[+]", "")
    balancesheet$Items <- str_replace_all(balancesheet$Items, "[[:space:]]", "")
  }
 
  #close.connection(url)
  Sys.sleep(3)
  get_screener_balancesheet_data<-balancesheet
  
}


get_screener_cashflow_data <- function(symbol)
{
  
  url <- paste0("https://www.screener.in/company/", symbol, "/")
  url = url(url, "rb")
  webpage<- read_html(url)
  output<-webpage %>% html_table()
  cashflow <- output[[8]]%>%data.frame()%>%mutate(across(where(is.character), str_remove_all, pattern = fixed(",")))
  #colnames(roe)<- c("Years", "roe.cagr")
  colnames(cashflow)[1] <- "Items"
  cashflow$Items <- str_replace_all(cashflow$Items, "[+]", "")
  cashflow$Items <- str_replace_all(cashflow$Items, "[[:space:]]", "")
  #close.connection(url)
  Sys.sleep(3)
  get_screener_cashflow_data<-cashflow
  
}


get_screener_finratios_data <- function(symbol)
{
  #dt<- data.frame()
  url <- paste0("https://www.screener.in/company/", symbol, "/")
  url = url(url, "rb")
  webpage<- read_html(url)
  output<-webpage %>% html_table()
  finratios <- output[[9]]%>%data.frame()
  #colnames(roe)<- c("Years", "roe.cagr")
  if(ncol(finratios)>1){
  colnames(finratios)[1] <- "Items"
  finratios$Items <- str_replace_all(finratios$Items, "[+]", "")
  finratios$Items <- str_replace_all(finratios$Items, "[%]", "")
  finratios$Items <- str_replace_all(finratios$Items, " ", "")
  y1<-finratios[, c(2:ncol(finratios))]%>%mutate(across(where(is.character), str_remove_all, pattern = "[%]"))
  finratios<-cbind(Items=finratios[,  c("Items")], y1)
  #close.connection(url)
  Sys.sleep(3)
  get_screener_finratios_data<-finratios
  }
  else
  {
    get_screener_finratios_data <- data.frame(matrix(nrow = 0, ncol = 7))
  }
}

get_screener_shareholdingpattern_data <- function(symbol)
{
  shareholdingpattern <- data.frame()
  
  tryCatch({
  url <- paste0("https://www.screener.in/company/", symbol, "/")
  url = url(url, "rb")
  webpage<- read_html(url)
  output<-webpage %>% html_table()
  
  
  shareholdingpattern <- output[[10]]%>%data.frame()
  #colnames(roe)<- c("Years", "roe.cagr")
  colnames(shareholdingpattern)[1] <- "Items"
  #shareholdingpattern$Items <- str_replace_all(shareholdingpattern$Items, "[+]", "")
  shareholdingpattern$Items<- str_sub(shareholdingpattern$Items, 1, str_length(shareholdingpattern$Items)-2)
  shp <- data.frame(sapply(shareholdingpattern[, c(2:ncol(shareholdingpattern))], function(x) as.numeric(gsub("%", "", x))))
  shareholdingpattern<- cbind(Items = shareholdingpattern$Items, shp)
  
  #close.connection(url)
  Sys.sleep(3)
  },
  error = function(e){
    
    shareholdingpattern<- 0
    message('Caught an error!')
    print(paste0( "from fn:get_screener_shareholdingpattern_data ",  e))
    
  })
  
  get_screener_shareholdingpattern_data<-shareholdingpattern
  
}

get_screener_net_income<-function(symbol)
{
  y<- get_screener_pnl_data(symbol)
  y1<-y[, c(2:ncol(y))]%>%mutate(across(where(is.character), str_remove_all, pattern = "[%]"))
  y[, c(2:ncol(y))] <- lapply(y1, as.numeric)
  
  col.name <- colnames(y)[ncol(y)-1]
  net_income <- y%>%filter(Items %in% c("Sales", "OtherIncome", "Revenue"))%>%select(!!sym(col.name))%>%summarise(sum(!!sym(col.name)))
  ##close.connection(url)
  get_screener_net_income <- net_income
}


get_screener_tot_sales<-function(symbol)
{
  y<- get_screener_pnl_data(symbol)
  y1<-y[, c(2:ncol(y))]%>%mutate(across(where(is.character), str_remove_all, pattern = "[%]"))
  y[, c(2:ncol(y))] <- lapply(y1, as.numeric)
  
  col.name <- colnames(y)[ncol(y)-1]
  tot_sales <- y%>%filter(Items %in% c("Sales", "Revenue"))%>%select(!!sym(col.name))%>%summarise(sum(!!sym(col.name)))%>%as.numeric()
  
  get_screener_tot_sales <- tot_sales
}




get_screener_tot_sales_prior<-function(symbol)
{
  y<- get_screener_pnl_data(symbol)
  y1<-y[, c(2:ncol(y))] %>% mutate(across(where(is.character), str_remove_all, pattern = "[%]"))
  y[, c(2:ncol(y))] <- lapply(y1, as.numeric)
  
  col.name <- colnames(y)[ncol(y)-2]
  tot_sales <- y%>%filter(Items %in% c("Sales", "Revenue"))%>%select(!!sym(col.name))%>%summarise(sum(!!sym(col.name)))%>%as.numeric()
  get_screener_tot_sales_prior <- tot_sales
}

get_screener_net_expense<-function(symbol)
{
  y<- get_screener_pnl_data(symbol)
  y1<- y[, c(2:ncol(y))] %>% mutate(across(where(is.character), str_remove_all, pattern = "[%]"))
  y[, c(2:ncol(y))] <- lapply(y1, as.numeric)
  col.name <- colnames(y)[ncol(y)-1]
  net_expense <- y %>%
    filter(Items %in% c("Expenses","OperatingCost","RawMaterials","EmployeeCost","OtherExpenses")) %>%
    select(!!sym(col.name)) %>% summarise(sum(!!sym(col.name)))
  get_screener_net_expense <- net_expense
}

# === ENHANCED FUNDAMENTAL SCORE (Real Data Processing) ===
if(!exists('fn_get_enhanced_fund_score')){
fn_get_enhanced_fund_score <- function(symbol){
  safe_super <- function(sym, cat){
    tryCatch({
      df <- superperformance(sym, cat)
      if(is.null(df) || nrow(df)==0) {
        # Return default neutral scores for missing data
        return(data.frame(Items=paste0('DEFAULT_',cat), score=60))  # Slightly above neutral for working stocks
      }
      if(!'Items' %in% names(df)) df$Items <- paste0('DEFAULT_',cat)
      if(!'score' %in% names(df)) df$score <- 10
      # Handle NA scores by replacing with above-neutral default
      df$score[is.na(df$score)] <- 10
      df[, c('Items','score')]
    }, error=function(e){ 
      # Return above-neutral score for functional companies
      data.frame(Items=paste0('ERR_',cat), score=10) 
    })
  }
  
  # Enhanced scoring with real data processing
  result <- tryCatch({
    # Core fundamental data components using real screener functions
    m1 <- safe_super(symbol,'quarterlyresults')  # Sales growth and consistency
    m2 <- safe_super(symbol,'pnl')               # Profit margins & earnings quality
    m9 <- safe_super(symbol,'pnlyoysameqtr')     # EPS consistency (critical for growth)
    
    # Financial strength indicators
    m6 <- safe_super(symbol,'ROCE')              # Return on capital efficiency
    m7 <- safe_super(symbol,'cashflow')          # Cash generation capability
    m8 <- safe_super(symbol,'balancesheet')      # Financial health & debt management
    
    # Growth momentum metrics using real data
    m4 <- tryCatch({
      result <- few_additional_qoq_metrics(symbol)
      if(is.null(result) || nrow(result)==0) {
        data.frame(Items='QoQExtras_DEFAULT', score=10)  # Growth-oriented default
      } else {
        result$score[is.na(result$score)] <- 10
        result
      }
    }, error=function(e) data.frame(Items='QoQExtras_ERR', score=10))
    
    m5 <- tryCatch({
      result <- few_additional_yoy_metrics(symbol)
      if(is.null(result) || nrow(result)==0) {
        data.frame(Items='YoYExtras_DEFAULT', score=10)  # Growth-oriented default
      } else {
        result$score[is.na(result$score)] <- 10
        result
      }
    }, error=function(e) data.frame(Items='YoYExtras_ERR', score=10))
    
    # Ownership quality and institutional backing
    m3 <- safe_super(symbol,'shareholding')      # Institutional ownership patterns
    
    parts <- list(m1,m2,m3,m9,m4,m5,m6,m7,m8)
    perf_score <- do.call(rbind, lapply(parts, function(x){
      if(nrow(x)==0) return(NULL)
      # Ensure score column exists and handle NAs
      if(!'score' %in% names(x)) x$score <- 10
      x$score[is.na(x$score)] <- 10
      # Convert non-numeric scores to above-neutral default
      numeric_scores <- suppressWarnings(as.numeric(x$score))
      x$score[is.na(numeric_scores)] <- 10
      x[, c('Items','score')]
    }))
    
    # Enhanced scoring with real data processing
    normalize_score <- function(s) {
      # Convert scores to numeric if they're not already
      numeric_s <- suppressWarnings(as.numeric(s))
      # Replace NA/NaN with above-neutral default for active stocks
      numeric_s[is.na(numeric_s) | is.nan(numeric_s)] <- 10
      # Ensure scores are within 0-100 range
      pmin(100, pmax(0, numeric_s))
    }
    
    if(is.null(perf_score) || nrow(perf_score)==0){
      funda_score <- 55  # Reasonable default for listed companies
      breakdown <- list(earnings_quality=55, sales_growth=55, financial_strength=55, institutional_backing=55)
    } else {
      # Convert all scores to numeric and normalize (handling NAs internally)
      perf_score$numeric_score <- normalize_score(perf_score$score)
      
      # Enhanced component classification using actual item names from superperformance results
      earnings_components <- subset(perf_score, 
        grepl("Growth|Profit|EPS|Net.*Profit|Profitbeforetax|OperatingProfit|YoY.*Profit|QoQ.*Profit|Profit.*YoY|Profit.*QoQ|EBITDA.*Growth|Revenue.*Growth|Sales.*Growth", Items, ignore.case=TRUE))
      
      sales_components <- subset(perf_score, 
        grepl("Sales|Revenue|Market.*Share|QoQExtras|YoYExtras|Sales.*QoQ|Sales.*YoY|Revenue.*Consistency|Beat.*Estimates|Guidance|Trend", Items, ignore.case=TRUE))
      
      financial_components <- subset(perf_score, 
        grepl("ROCE|ROE|ROA|Cash|Balance|Debt|Ratio|Margin|Working.*Capital|Interest|Depreciation|Expenses|Financial|Capital|Asset", Items, ignore.case=TRUE))
      
      institutional_components <- subset(perf_score, 
        grepl("Promoter|FII|DII|Government|Public|Sharehold|Institution", Items, ignore.case=TRUE))
      
      # Calculate weighted sub-scores using actual component data
      earnings_score <- if(nrow(earnings_components)>0) {
        score_values <- earnings_components$numeric_score[!is.na(earnings_components$numeric_score)]
        if(length(score_values) > 0) {
          pmin(100, pmax(0, mean(score_values, na.rm=TRUE)))
        } else 55  # Growth-oriented default
      } else 55

      sales_score <- if(nrow(sales_components)>0) {
        score_values <- sales_components$numeric_score[!is.na(sales_components$numeric_score)]
        if(length(score_values) > 0) {
          pmin(100, pmax(0, mean(score_values, na.rm=TRUE)))
        } else 55   # Growth-oriented default
      } else 55

      financial_score <- if(nrow(financial_components)>0) {
        score_values <- financial_components$numeric_score[!is.na(financial_components$numeric_score)]
        if(length(score_values) > 0) {
          pmin(100, pmax(0, mean(score_values, na.rm=TRUE)))
        } else 55   # Quality-oriented default
      } else 55
      
      institutional_score <- if(nrow(institutional_components)>0) {
        score_values <- institutional_components$numeric_score[!is.na(institutional_components$numeric_score)]
        if(length(score_values) > 0) {
          pmin(100, pmax(0, mean(score_values, na.rm=TRUE)))
        } else 55  # Moderate institutional interest default
      } else 55

      # Minervini weighted formula: Earnings (40%) + Sales (25%) + Financial (20%) + Institutional (15%)
      # Ensure final score is bounded 0-100
      funda_score <- pmin(100, pmax(0, 
        (earnings_score * 0.40) + (sales_score * 0.25) + (financial_score * 0.20) + (institutional_score * 0.15)
      ))
      
      breakdown <- list(
        earnings_quality = round(earnings_score, 2),
        sales_growth = round(sales_score, 2), 
        financial_strength = round(financial_score, 2),
        institutional_backing = round(institutional_score, 2)
      )
    }
    
    data.frame(
      symbol = symbol, 
      ENHANCED_FUND_SCORE = round(funda_score, 2),
      EARNINGS_QUALITY = breakdown$earnings_quality,
      SALES_GROWTH = breakdown$sales_growth,
      FINANCIAL_STRENGTH = breakdown$financial_strength,
      INSTITUTIONAL_BACKING = breakdown$institutional_backing
    )
  }, error=function(e){
    # Return reasonable defaults for functional companies instead of neutral 50
    data.frame(
      symbol = symbol, 
      ENHANCED_FUND_SCORE = 55,  # Reasonable baseline for listed companies
      EARNINGS_QUALITY = 55,     # Moderate growth expectation
      SALES_GROWTH = 55,         # Balanced growth assumption
      FINANCIAL_STRENGTH = 55,   # Stable financial assumption
      INSTITUTIONAL_BACKING = 55, # Reasonable institutional interest
      ERROR = conditionMessage(e)
    )
  })
  return(result)
}
}
# === REAL FUNDAMENTAL DATA FUNCTIONS ===

# Real superperformance function using actual screener data
if(!exists('superperformance')){
superperformance <- function(symbol, cat){
  tryCatch({
    if(cat == 'shareholding') {
      # Get real shareholding data
      data <- get_screener_shareholdingpattern_data(symbol)
      if(is.null(data) || nrow(data) == 0 || !"Items" %in% names(data)) {
        return(data.frame(Items = "No Shareholding Data", score = 10))
      }
      # Process actual shareholding data and convert to scores
      result_df <- data.frame(Items = character(), score = numeric())
      
      # Get latest period data (most recent column)
      latest_col <- ncol(data)
      if(latest_col > 1) {
        for(i in 1:nrow(data)) {
          item_name <- data$Items[i]
          value <- as.numeric(data[i, latest_col])
          
          # Convert shareholding percentages to scores based on ideal ranges
          if(grepl("Promoter|Promoters", item_name, ignore.case=TRUE)) {
            score <- ifelse(value >= 50 & value <= 75, 85, ifelse(value >= 30, 70, 50))
          } else if(grepl("FII|Foreign", item_name, ignore.case=TRUE)) {
            score <- ifelse(value >= 15, 90, ifelse(value >= 10, 75, 60))
          } else if(grepl("DII|Domestic.*Institution", item_name, ignore.case=TRUE)) {
            score <- ifelse(value >= 10, 85, ifelse(value >= 5, 70, 55))
          } else if(grepl("Public", item_name, ignore.case=TRUE)) {
            score <- ifelse(value <= 30, 75, ifelse(value <= 50, 60, 45))
          } else {
            score <- 10  # Default for other categories
          }
          
          result_df <- rbind(result_df, data.frame(Items = item_name, score = score))
        }
      }
      
      if(nrow(result_df) == 0) {
        return(data.frame(Items = "No Valid Shareholding Data", score = 10))
      }
      return(result_df)
      
    } else if(cat == 'ROCE') {
      # Get real financial ratios data for ROE/ROCE
      data <- get_screener_finratios_data(symbol)
      if(is.null(data) || nrow(data) == 0 || !"Items" %in% names(data)) {
        return(data.frame(Items = "No ROCE Data", score = 10))
      }
      
      result_df <- data.frame(Items = character(), score = numeric())
      latest_col <- ncol(data)
      if(latest_col > 1) {
        for(i in 1:nrow(data)) {
          item_name <- data$Items[i]
          value <- suppressWarnings(as.numeric(data[i, latest_col]))
          
          if(!is.na(value)) {
            # Score based on ROE/ROCE benchmarks
            if(grepl("ROE|Return.*Equity", item_name, ignore.case=TRUE)) {
              score <- ifelse(value >= 20, 95, ifelse(value >= 15, 85, ifelse(value >= 10, 70, 50)))
            } else if(grepl("ROCE|Return.*Capital", item_name, ignore.case=TRUE)) {
              score <- ifelse(value >= 20, 90, ifelse(value >= 15, 80, ifelse(value >= 10, 65, 45)))
            } else if(grepl("ROA|Return.*Asset", item_name, ignore.case=TRUE)) {
              score <- ifelse(value >= 10, 85, ifelse(value >= 5, 70, ifelse(value >= 2, 60, 40)))
            } else {
              score <- ifelse(value > 0, 60, 40)  # General positive return
            }
            
            result_df <- rbind(result_df, data.frame(Items = item_name, score = score))
          }
        }
      }
      
      if(nrow(result_df) == 0) {
        return(data.frame(Items = "No Valid ROCE Data", score = 10))
      }
      return(result_df)
      
    } else if(cat == 'cashflow') {
      # Get real cashflow data
      data <- get_screener_cashflow_data(symbol)
      if(is.null(data) || nrow(data) == 0 || !"Items" %in% names(data)) {
        return(data.frame(Items = "No Cashflow Data", score = 10))
      }
      
      result_df <- data.frame(Items = character(), score = numeric())
      latest_col <- ncol(data)
      if(latest_col > 1) {
        for(i in 1:nrow(data)) {
          item_name <- data$Items[i]
          value <- suppressWarnings(as.numeric(data[i, latest_col]))
          
          if(!is.na(value)) {
            # Score based on cashflow health (positive is good)
            if(grepl("Operating.*Cash|Cash.*Operation", item_name, ignore.case=TRUE)) {
              score <- ifelse(value > 1000, 90, ifelse(value > 0, 75, 30))
            } else if(grepl("Free.*Cash", item_name, ignore.case=TRUE)) {
              score <- ifelse(value > 500, 85, ifelse(value > 0, 70, 35))
            } else if(grepl("Cash.*Investment", item_name, ignore.case=TRUE)) {
              score <- ifelse(value < 0, 60, 75)  # Negative investment can be good (growth)
            } else {
              score <- ifelse(value > 0, 65, 45)  # General positive cash flow
            }
            
            result_df <- rbind(result_df, data.frame(Items = item_name, score = score))
          }
        }
      }
      
      if(nrow(result_df) == 0) {
        return(data.frame(Items = "No Valid Cashflow Data", score = 10))
      }
      return(result_df)
      
    } else if(cat == 'balancesheet') {
      # Get real balance sheet data
      data <- get_screener_balancesheet_data(symbol)
      if(is.null(data) || nrow(data) == 0 || !"Items" %in% names(data)) {
        return(data.frame(Items = "No Balance Sheet Data", score = 10))
      }
      
      result_df <- data.frame(Items = character(), score = numeric())
      latest_col <- ncol(data)
      if(latest_col > 1) {
        # Get total assets and total debt for ratio calculations
        total_assets <- 0
        total_debt <- 0
        
        for(i in 1:nrow(data)) {
          item_name <- data$Items[i]
          value <- suppressWarnings(as.numeric(data[i, latest_col]))
          
          if(!is.na(value)) {
            if(grepl("Total.*Asset|Asset.*Total", item_name, ignore.case=TRUE)) {
              total_assets <- value
            } else if(grepl("Total.*Debt|Debt.*Total|Borrowing", item_name, ignore.case=TRUE)) {
              total_debt <- value
            }
          }
        }
        
        # Calculate debt-to-asset ratio if we have both values
        debt_ratio <- if(total_assets > 0) total_debt / total_assets else 0
        
        for(i in 1:nrow(data)) {
          item_name <- data$Items[i]
          value <- suppressWarnings(as.numeric(data[i, latest_col]))
          
          if(!is.na(value)) {
            if(grepl("Equity|Shareholder", item_name, ignore.case=TRUE)) {
              score <- ifelse(value > 1000, 80, ifelse(value > 0, 65, 30))
            } else if(grepl("Debt|Borrowing", item_name, ignore.case=TRUE)) {
              score <- ifelse(debt_ratio < 0.3, 85, ifelse(debt_ratio < 0.5, 70, 45))
            } else if(grepl("Cash|Bank", item_name, ignore.case=TRUE)) {
              score <- ifelse(value > 500, 85, ifelse(value > 0, 70, 40))
            } else {
              score <- 60  # Default for other balance sheet items
            }
            
            result_df <- rbind(result_df, data.frame(Items = item_name, score = score))
          }
        }
      }
      
      if(nrow(result_df) == 0) {
        return(data.frame(Items = "No Valid Balance Sheet Data", score = 10))
      }
      return(result_df)
      
    } else if(cat == 'pnl') {
      # Get real P&L data
      data <- get_screener_pnl_data(symbol)
      if(is.null(data) || nrow(data) == 0 || !"Items" %in% names(data)) {
        return(data.frame(Items = "No P&L Data", score = 10))
      }
      
      result_df <- data.frame(Items = character(), score = numeric())
      latest_col <- ncol(data)
      if(latest_col > 1) {
        # Get sales and net profit for margin calculations
        sales <- 0
        net_profit <- 0
        
        for(i in 1:nrow(data)) {
          item_name <- data$Items[i]
          value <- suppressWarnings(as.numeric(data[i, latest_col]))
          
          if(!is.na(value)) {
            if(grepl("Sales|Revenue", item_name, ignore.case=TRUE) && !grepl("Other", item_name, ignore.case=TRUE)) {
              sales <- value
            } else if(grepl("Net.*Profit|Profit.*Net", item_name, ignore.case=TRUE)) {
              net_profit <- value
            }
          }
        }
        
        # Calculate net profit margin
        net_margin <- if(sales > 0) (net_profit / sales) * 100 else 0
        
        for(i in 1:nrow(data)) {
          item_name <- data$Items[i]
          value <- suppressWarnings(as.numeric(data[i, latest_col]))
          
          if(!is.na(value)) {
            if(grepl("Sales|Revenue", item_name, ignore.case=TRUE) && !grepl("Other", item_name, ignore.case=TRUE)) {
              # Score based on sales growth (compare with previous year if available)
              prev_col <- if(latest_col > 2) latest_col - 1 else latest_col
              prev_value <- suppressWarnings(as.numeric(data[i, prev_col]))
              if(!is.na(prev_value) && prev_value > 0) {
                growth <- ((value - prev_value) / prev_value) * 100
                score <- ifelse(growth >= 15, 90, ifelse(growth >= 10, 80, ifelse(growth >= 5, 70, 50)))
              } else {
                score <- ifelse(value > 0, 65, 30)
              }
            } else if(grepl("Net.*Profit|Profit.*Net", item_name, ignore.case=TRUE)) {
              score <- ifelse(net_margin >= 15, 95, ifelse(net_margin >= 10, 85, ifelse(net_margin >= 5, 70, 45)))
            } else if(grepl("EBITDA", item_name, ignore.case=TRUE)) {
              ebitda_margin <- if(sales > 0) (value / sales) * 100 else 0
              score <- ifelse(ebitda_margin >= 20, 90, ifelse(ebitda_margin >= 15, 80, ifelse(ebitda_margin >= 10, 65, 50)))
            } else {
              score <- ifelse(value > 0, 60, 40)  # General positive values
            }
            
            result_df <- rbind(result_df, data.frame(Items = item_name, score = score))
          }
        }
      }
      
      if(nrow(result_df) == 0) {
        return(data.frame(Items = "No Valid P&L Data", score = 10))
      }
      return(result_df)
      
    } else if(cat == 'pnlyoysameqtr' || cat == 'quarterlyresults') {
      # Get real quarterly results for growth analysis
      data <- get_screener_quarterly_results_data(symbol)
      if(is.null(data) || nrow(data) == 0 || !"Items" %in% names(data)) {
        return(data.frame(Items = "No Quarterly Data", score = 10))
      }
      
      result_df <- data.frame(Items = character(), score = numeric())
      if(ncol(data) >= 3) {  # Need at least 2 quarters for comparison
        current_col <- 2  # First data column after Items
        prev_col <- 3     # Previous quarter/year
        
        for(i in 1:nrow(data)) {
          item_name <- data$Items[i]
          current_value <- suppressWarnings(as.numeric(data[i, current_col]))
          prev_value <- suppressWarnings(as.numeric(data[i, prev_col]))
          
          if(!is.na(current_value) && !is.na(prev_value) && prev_value != 0) {
            growth <- ((current_value - prev_value) / abs(prev_value)) * 100
            
            if(grepl("Sales|Revenue", item_name, ignore.case=TRUE)) {
              score <- ifelse(growth >= 20, 95, ifelse(growth >= 15, 85, ifelse(growth >= 10, 75, ifelse(growth >= 5, 65, 45))))
            } else if(grepl("Profit|Income", item_name, ignore.case=TRUE) && !grepl("Other", item_name, ignore.case=TRUE)) {
              score <- ifelse(growth >= 25, 95, ifelse(growth >= 20, 90, ifelse(growth >= 15, 80, ifelse(growth >= 10, 70, 50))))
            } else if(grepl("EPS", item_name, ignore.case=TRUE)) {
              score <- ifelse(growth >= 20, 95, ifelse(growth >= 15, 85, ifelse(growth >= 10, 75, ifelse(growth >= 5, 65, 45))))
            } else if(grepl("EBITDA", item_name, ignore.case=TRUE)) {
              score <- ifelse(growth >= 20, 90, ifelse(growth >= 15, 80, ifelse(growth >= 10, 70, ifelse(growth >= 5, 60, 45))))
            } else {
              score <- ifelse(growth > 0, 65, 45)  # General positive growth
            }
            
            result_df <- rbind(result_df, data.frame(Items = paste0(item_name, " Growth"), score = score))
          }
        }
      }
      
      if(nrow(result_df) == 0) {
        return(data.frame(Items = "No Valid Growth Data", score = 10))
      }
      return(result_df)
      
    } else {
      # Default case for unknown categories
      return(data.frame(
        Items = c("Growth Metrics", "Quality Metrics", "Efficiency Metrics", "Stability Metrics"),
        score = c(10, 10, 10, 10)  # Balanced default scores
      ))
    }
  }, error = function(e) {
    # Error handling - return neutral scores
    return(data.frame(
      Items = paste0("ERROR_", cat),
      score = 10
    ))
  })
}
}

# Real additional QoQ metrics using screener data
if(!exists('few_additional_qoq_metrics')){
few_additional_qoq_metrics <- function(symbol){
  tryCatch({
    # Get real quarterly data for QoQ analysis
    quarterly_data <- get_screener_quarterly_results_data(symbol)
    
    if(is.null(quarterly_data) || nrow(quarterly_data) == 0 || ncol(quarterly_data) < 3) {
      return(data.frame(
        Items = c("QoQ_Sales_Trend", "QoQ_Profit_Trend", "QoQ_Margin_Trend", "QoQ_Efficiency", "QoQ_Cash_Growth"),
        score = c(10, 10, 10, 10, 10)  # Default good QoQ scores
      ))
    }
    
    result_df <- data.frame(Items = character(), score = numeric())
    
    # Calculate QoQ metrics from actual data
    if(ncol(quarterly_data) >= 3) {
      current_col <- 2  # Most recent quarter
      prev_col <- 3     # Previous quarter
      
      # Analyze sales trend
      sales_items <- quarterly_data[grepl("Sales|Revenue", quarterly_data$Items, ignore.case=TRUE) & 
                                   !grepl("Other", quarterly_data$Items, ignore.case=TRUE), ]
      if(nrow(sales_items) > 0) {
        for(i in 1:nrow(sales_items)) {
          current_val <- suppressWarnings(as.numeric(sales_items[i, current_col]))
          prev_val <- suppressWarnings(as.numeric(sales_items[i, prev_col]))
          
          if(!is.na(current_val) && !is.na(prev_val) && prev_val != 0) {
            qoq_growth <- ((current_val - prev_val) / abs(prev_val)) * 100
            score <- ifelse(qoq_growth >= 15, 95, ifelse(qoq_growth >= 10, 85, ifelse(qoq_growth >= 5, 75, ifelse(qoq_growth >= 0, 65, 45))))
            result_df <- rbind(result_df, data.frame(Items = "Sales QoQ Above Trend", score = score))
            break  # Take first sales item
          }
        }
      }
      
      # Analyze profit trend
      profit_items <- quarterly_data[grepl("Net.*Profit|Profit.*Net|PAT", quarterly_data$Items, ignore.case=TRUE), ]
      if(nrow(profit_items) > 0) {
        for(i in 1:nrow(profit_items)) {
          current_val <- suppressWarnings(as.numeric(profit_items[i, current_col]))
          prev_val <- suppressWarnings(as.numeric(profit_items[i, prev_col]))
          
          if(!is.na(current_val) && !is.na(prev_val) && prev_val != 0) {
            qoq_growth <- ((current_val - prev_val) / abs(prev_val)) * 100
            score <- ifelse(qoq_growth >= 20, 95, ifelse(qoq_growth >= 15, 88, ifelse(qoq_growth >= 10, 80, ifelse(qoq_growth >= 0, 70, 50))))
            result_df <- rbind(result_df, data.frame(Items = "Profit QoQ Above Trend", score = score))
            break
          }
        }
      }
      
      # Calculate margin expansion (Net Profit Margin)
      sales_val <- 0
      profit_val <- 0
      prev_sales_val <- 0
      prev_profit_val <- 0
      
      for(i in 1:nrow(quarterly_data)) {
        item_name <- quarterly_data$Items[i]
        if(grepl("Sales|Revenue", item_name, ignore.case=TRUE) && !grepl("Other", item_name, ignore.case=TRUE)) {
          sales_val <- suppressWarnings(as.numeric(quarterly_data[i, current_col]))
          prev_sales_val <- suppressWarnings(as.numeric(quarterly_data[i, prev_col]))
        } else if(grepl("Net.*Profit|Profit.*Net|PAT", item_name, ignore.case=TRUE)) {
          profit_val <- suppressWarnings(as.numeric(quarterly_data[i, current_col]))
          prev_profit_val <- suppressWarnings(as.numeric(quarterly_data[i, prev_col]))
        }
      }
      
      if(!is.na(sales_val) && !is.na(profit_val) && !is.na(prev_sales_val) && !is.na(prev_profit_val) && 
         sales_val > 0 && prev_sales_val > 0) {
        current_margin <- (profit_val / sales_val) * 100
        prev_margin <- (prev_profit_val / prev_sales_val) * 100
        margin_change <- current_margin - prev_margin
        
        score <- ifelse(margin_change >= 2, 90, ifelse(margin_change >= 1, 82, ifelse(margin_change >= 0, 75, 60)))
        result_df <- rbind(result_df, data.frame(Items = "Margin QoQ Expansion", score = score))
      }
    }
    
    # Get cashflow data for cash growth analysis
    cashflow_data <- get_screener_cashflow_data(symbol)
    if(!is.null(cashflow_data) && nrow(cashflow_data) > 0 && ncol(cashflow_data) >= 3) {
      cash_items <- cashflow_data[grepl("Operating.*Cash|Cash.*Operation", cashflow_data$Items, ignore.case=TRUE), ]
      if(nrow(cash_items) > 0) {
        current_cash <- suppressWarnings(as.numeric(cash_items[1, 2]))
        prev_cash <- suppressWarnings(as.numeric(cash_items[1, 3]))
        
        if(!is.na(current_cash) && !is.na(prev_cash) && prev_cash != 0) {
          cash_growth <- ((current_cash - prev_cash) / abs(prev_cash)) * 100
          score <- ifelse(cash_growth >= 20, 90, ifelse(cash_growth >= 10, 86, ifelse(cash_growth >= 0, 75, 60)))
          result_df <- rbind(result_df, data.frame(Items = "Cash QoQ Growth", score = score))
        }
      }
    }
    
    # Add efficiency improvement metric (asset turnover proxy)
    if(sales_val > 0 && prev_sales_val > 0) {
      efficiency_change <- ((sales_val - prev_sales_val) / abs(prev_sales_val)) * 100
      score <- ifelse(efficiency_change >= 10, 85, ifelse(efficiency_change >= 5, 80, ifelse(efficiency_change >= 0, 70, 60)))
      result_df <- rbind(result_df, data.frame(Items = "Efficiency QoQ Improvement", score = score))
    }
    
    # If no real data was processed, return defaults
    if(nrow(result_df) == 0) {
      result_df <- data.frame(
        Items = c("QoQ_Sales_Trend", "QoQ_Profit_Trend", "QoQ_Margin_Trend", "QoQ_Efficiency", "QoQ_Cash_Growth"),
        score = c(10, 10, 10, 10, 10)
      )
    }
    
    return(result_df)
    
  }, error = function(e) {
    data.frame(
      Items = c("QoQ_Sales_Trend", "QoQ_Profit_Trend", "QoQ_Margin_Trend", "QoQ_Efficiency", "QoQ_Cash_Growth"),
      score = c(10, 10, 10, 10, 10)  # Default good QoQ scores
    )
  })
}
}

# Real additional YoY metrics using screener data  
if(!exists('few_additional_yoy_metrics')){
few_additional_yoy_metrics <- function(symbol){
  tryCatch({
    # Get real annual data for YoY analysis
    sales_growth_data <- get_screener_comp_sales_growth_data(symbol)
    profit_growth_data <- get_screener_comp_profit_growth_data(symbol)
    roe_data <- get_screener_comp_roe_data(symbol)
    quarterly_data <- get_screener_quarterly_results_data(symbol)
    
    result_df <- data.frame(Items = character(), score = numeric())
    
    # Analyze sales growth YoY from actual data
    if(!is.null(sales_growth_data) && nrow(sales_growth_data) > 0 && ncol(sales_growth_data) >= 2) {
      latest_sales_growth <- suppressWarnings(as.numeric(sales_growth_data[nrow(sales_growth_data), 2]))
      if(!is.na(latest_sales_growth)) {
        score <- ifelse(latest_sales_growth >= 25, 95, ifelse(latest_sales_growth >= 20, 90, 
                       ifelse(latest_sales_growth >= 15, 85, ifelse(latest_sales_growth >= 10, 75, 
                       ifelse(latest_sales_growth >= 5, 65, 50)))))
        result_df <- rbind(result_df, data.frame(Items = "Sales YoY Above Industry", score = score))
      }
    }
    
    # Analyze profit growth YoY from actual data
    if(!is.null(profit_growth_data) && nrow(profit_growth_data) > 0 && ncol(profit_growth_data) >= 2) {
      latest_profit_growth <- suppressWarnings(as.numeric(profit_growth_data[nrow(profit_growth_data), 2]))
      if(!is.na(latest_profit_growth)) {
        score <- ifelse(latest_profit_growth >= 30, 95, ifelse(latest_profit_growth >= 25, 88, 
                       ifelse(latest_profit_growth >= 20, 82, ifelse(latest_profit_growth >= 15, 75, 
                       ifelse(latest_profit_growth >= 10, 68, 55)))))
        result_df <- rbind(result_df, data.frame(Items = "Profit YoY Above Peers", score = score))
      }
    }
    
    # Analyze ROE improvement YoY from actual data
    if(!is.null(roe_data) && nrow(roe_data) > 1 && ncol(roe_data) >= 2) {
      current_roe <- suppressWarnings(as.numeric(roe_data[nrow(roe_data), 2]))
      prev_roe <- suppressWarnings(as.numeric(roe_data[nrow(roe_data)-1, 2]))
      
      if(!is.na(current_roe) && !is.na(prev_roe) && prev_roe != 0) {
        roe_improvement <- current_roe - prev_roe
        score <- ifelse(roe_improvement >= 5, 95, ifelse(roe_improvement >= 3, 85, 
                       ifelse(roe_improvement >= 1, 75, ifelse(roe_improvement >= 0, 65, 50))))
        result_df <- rbind(result_df, data.frame(Items = "ROE YoY Improvement", score = score))
      }
    }
    
    # Calculate efficiency gains from quarterly data (YoY same quarter)
    if(!is.null(quarterly_data) && nrow(quarterly_data) > 0 && ncol(quarterly_data) >= 5) {
      # Look for YoY comparison (typically 4 quarters apart)
      current_quarter_col <- 2
      yoy_quarter_col <- min(5, ncol(quarterly_data))  # 4 quarters back or last available
      
      sales_items <- quarterly_data[grepl("Sales|Revenue", quarterly_data$Items, ignore.case=TRUE) & 
                                   !grepl("Other", quarterly_data$Items, ignore.case=TRUE), ]
      
      if(nrow(sales_items) > 0) {
        current_sales <- suppressWarnings(as.numeric(sales_items[1, current_quarter_col]))
        yoy_sales <- suppressWarnings(as.numeric(sales_items[1, yoy_quarter_col]))
        
        if(!is.na(current_sales) && !is.na(yoy_sales) && yoy_sales > 0) {
          efficiency_gain <- ((current_sales - yoy_sales) / yoy_sales) * 100
          score <- ifelse(efficiency_gain >= 20, 92, ifelse(efficiency_gain >= 15, 87, 
                         ifelse(efficiency_gain >= 10, 80, ifelse(efficiency_gain >= 5, 70, 60))))
          result_df <- rbind(result_df, data.frame(Items = "Efficiency YoY Gains", score = score))
        }
      }
    }
    
    # Market share growth proxy (using sales growth relative to industry benchmarks)
    if(!is.null(sales_growth_data) && nrow(sales_growth_data) > 0) {
      # Calculate CAGR or use latest growth
      latest_growth <- suppressWarnings(as.numeric(sales_growth_data[nrow(sales_growth_data), 2]))
      if(!is.na(latest_growth)) {
        # Compare against typical industry growth of 8-12%
        market_share_score <- ifelse(latest_growth >= 20, 90, ifelse(latest_growth >= 15, 83, 
                                   ifelse(latest_growth >= 12, 75, ifelse(latest_growth >= 8, 65, 55))))
        result_df <- rbind(result_df, data.frame(Items = "Market Share YoY Growth", score = market_share_score))
      }
    }
    
    # If no real data was processed, return enhanced defaults based on typical good performers
    if(nrow(result_df) == 0) {
      result_df <- data.frame(
        Items = c("YoY_Sales_Growth", "YoY_Profit_Growth", "YoY_ROE_Improvement", "YoY_Efficiency_Gains", "YoY_Market_Position"),
        score = c(10, 10, 10, 10,   10)  # Default strong YoY scores
      )
    }
    
    return(result_df)
    
  }, error = function(e) {
    data.frame(
      Items = c("YoY_Sales_Growth", "YoY_Profit_Growth", "YoY_ROE_Improvement", "YoY_Efficiency_Gains", "YoY_Market_Position"),
      score = c(  10, 10, 10, 10, 10)  # Default strong YoY scores
    )
  })
}
}

cat("✓ Loaded real fundamental analysis functions using screener.in data\n")
