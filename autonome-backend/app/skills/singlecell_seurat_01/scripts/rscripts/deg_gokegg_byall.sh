mkdir -p gokegg_up
cat *filter_up* | cut -f 1 | sort | uniq  > filter_up_deg_sort.txt 
perl -e 'print "perl /Users/chengchao/biosource/besaltbio/GO_and_KEGG/kegg_go_pipe_one.pl -gene ../filter_up_deg_sort.txt -go '"$1"' -col 1 -sp '"$2"' -pre up -p 1 &\n";' > gokegg_up/gokegg.sh 
cd gokegg_up && sh gokegg.sh &

mkdir -p gokegg_down
cat *filter_down* | cut -f 1 | sort | uniq  > filter_down_deg_sort.txt 
perl -e 'print "perl /Users/chengchao/biosource/besaltbio/GO_and_KEGG/kegg_go_pipe_one.pl -gene ../filter_down_deg_sort.txt -go '"$1"' -col 1 -sp '"$2"' -pre down -p 1 &\n";' > gokegg_down/gokegg.sh 
cd gokegg_down && sh gokegg.sh &

wait