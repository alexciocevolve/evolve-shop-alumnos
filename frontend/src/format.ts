const euros = new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR" });
const dates = new Intl.DateTimeFormat("en-IE", { dateStyle: "medium", timeStyle: "short" });

// The API sends money as integer cents; this is the only place they become euros.
export const formatPrice = (cents: number) => euros.format(cents / 100);

export const formatDate = (iso: string) => dates.format(new Date(iso));

// Just the day, for the ends of a chart axis. The full date and time are in the table
// under it and in each point's tooltip: an axis label is a signpost, not a record.
const days = new Intl.DateTimeFormat("en-IE", { dateStyle: "medium" });

export const formatDay = (iso: string) => days.format(new Date(iso));

// The clock alone, for when every change on a chart happened the same day and repeating
// the date at both ends would say nothing twice.
const clock = new Intl.DateTimeFormat("en-IE", { timeStyle: "short" });

export const formatTime = (iso: string) => clock.format(new Date(iso));
