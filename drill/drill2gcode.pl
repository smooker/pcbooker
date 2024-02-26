#!/usr/bin/perl

use strict;
use warnings;

my $file=$ARGV[0];

my $repfile = $ARGV[1];

open REP, "<$repfile";


my @drills;

while (<REP>) {
#   print $_;
   if ( $_ =~ m/(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+/) {
   	print $1."\t".$2."\t".$3."\t".$4."\t".$5."\t".$6."\t".$7."\n";
	$drills[$7] = $1*0.0254;
   }
}

for my $i (0 .. $#drills) {
	print "T$i = ".$drills[$i]."mm\n";
}

close REP;


#exit();


open OFILE, ">output.ngc";

print OFILE "%\nM3\nG21\nG01 X0Y0Z0F1000\nM03 S200\n";


#diameter of tool 2mm
#diameter of cut 6mm
#4mm diameter from center of tool + 1 + 1 = 6mm
#G00 X0 Y0
#G02 X-2 Y0 Z0 I2 J0
#I, J – The arc’s center point relative to X, Y.
#
sub drillHelix
{
	my $x = shift;
	my $y = shift;
	my $z = shift;

	my $diam = shift;
	my $toold = shift;

	my $x1 = $x-($diam/2)+$toold/2;
	my $i1 = $diam/2-$toold/2;

	print OFILE "G01 X".$x1." Y".$y." Z".$z."\n" ; #here smooker
	for (my $z1=$z; $z1>$z-2.0; $z1-=0.1) {
		print OFILE "G02 X".$x1. " Y".$y." Z".$z1." I".$i1. " J0\n";	
	}
	print OFILE "G01 Z".$z."\n" ; #here smooker
}

sub addzero 
{
	my $num = shift;

	for(my $i=length($num);$i<5;$i++)
 {
	  $num .= "0";
 }
	return $num;	
}

open FILE, "<$file";

my $x = 0;
my $y = 0;

my $helixflag = 0;

my $toolnum = 0;

while(<FILE>)
{
	print $_;
	my $flag = 0;

	if ( $_ =~ m/^T(\d+)/)
	{
		#print "OLELE: X=$x Y=$y\n"
		print OFILE "T$1\n";
		print OFILE "M06\n";
		if ($drills[$1] > 3.00) {
			print "VGZ ok > 3mm\n";
			$helixflag = 1;
			$toolnum = $1;
		} else {
			$helixflag = 0;
		}
	}

	if ( $_ =~ m/X(\d+)Y(\d+)/)
	{
		$x = addzero($1)*0.0254;
		$y = addzero($2)*0.0254;
		#print "OLELE: X=$x Y=$y\n"
		$flag = 1;
	}
	if ( $_ =~ m/X(\d+)/ ) {
		$x = addzero($1)*0.0254;	
		$flag = 1;
	}
  	if ( $_ =~ m/Y(\d+)/ ) {
    		$y = addzero($1)*0.0254;
		$flag = 1;
 	}
	if ($flag == 1 & $helixflag == 0) {
		print("OLELE: $x:$y\n");
		print OFILE "G01 X".$x."Y".$y." F1000\n";
		print OFILE "G01 Z-14.5 F100\n";
    		print OFILE "G01 Z-11.0 F100\n";
	}
	if ($flag == 1 & $helixflag == 1) {
		drillHelix($x, $y, -11.0, 1.5, $drills[$toolnum]);
	}
}

print OFILE "G01 X0Y0Z0F1000\n";

close FILE;
close OFILE;
