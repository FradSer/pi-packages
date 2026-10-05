export function indexById(records, ids) { return ids.map(id => records.find(record => record.id === id)); }
