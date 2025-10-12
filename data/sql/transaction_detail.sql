select 
	t.transaction_date,
	a.name as account_name,
	c.name as category_name,
	t.amount,
	t.item_name,
	t.description,
	t.memo
from transactions t
join accounts a on t.account_id = a.id
left join categories c on t.category_id = c.id
left join data_logs l on t.log_id = l.id
where l.csvfile_id = ?
order by t.transaction_date