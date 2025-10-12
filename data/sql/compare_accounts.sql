---period,expense,transfer,total
with nicos_tbl as (
select 
	--- t.transaction_date as date,
	CASE WHEN CAST( strftime('%d',t.transaction_date) as integer) <= ? THEN date(t.transaction_date,'-1 months') ELSE t.transaction_date END as t_date,
	t.transfer_id as transfer_id,
	c.type as type,
	amount
from transactions t
join accounts a on t.account_id = a.id
left join categories c on t.category_id = c.id
where t.account_id = ?
order by t.transaction_date
) 
select 
	CASE when type='transfer' then strftime('%Y-%m',date(t_date,'-1 months')) ELSE strftime('%Y-%m',t_date) END as period,
	SUM( CASE when transfer_id is null then amount else 0 end ) as expense,
	SUM( CASE when transfer_id is not null then amount else 0 end ) as transfer,
	SUM(amount) as total
from nicos_tbl
group by period;