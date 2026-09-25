const euros = new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR" });
const dates = new Intl.DateTimeFormat("en-IE", { dateStyle: "medium", timeStyle: "short" });

// The API sends money as integer cents; this is the only place they become euros.
export const formatPrice = (cents: number) => euros.format(cents / 100);

export const formatDate = (iso: string) => dates.format(new Date(iso));
