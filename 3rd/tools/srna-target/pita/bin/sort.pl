#!/usr/bin/perl
use strict;
# Replacement for sort - reads stdin, sorts by numeric key if -kNn specified
my @lines = <STDIN>;
my $key_field = undef;
my $numeric = 0;
my @args = @ARGV;
while (@args) {
    my $a = shift @args;
    if ($a =~ /^-k(\d+)n$/) {
        $key_field = $1 - 1;  # 0-indexed
        $numeric = 1;
    } elsif ($a =~ /^-k(\d+)/) {
        $key_field = $1 - 1;
    }
}
if (defined($key_field)) {
    if ($numeric) {
        @lines = sort { 
            my @af = split(/\t/, $a); my @bf = split(/\t/, $b);
            ($af[$key_field] // 0) <=> ($bf[$key_field] // 0)
        } @lines;
    } else {
        @lines = sort {
            my @af = split(/\t/, $a); my @bf = split(/\t/, $b);
            ($af[$key_field] // '') cmp ($bf[$key_field] // '')
        } @lines;
    }
} else {
    @lines = sort @lines;
}
print for @lines;
