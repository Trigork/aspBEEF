import csv
import argparse
import os
import tempfile
import json
import warnings
from subprocess import PIPE, Popen
import pandas as pd
import numpy as np
from sklearn.model_selection import KFold

 # Experimental Fix to decimal numbers, probably have to deal with them dynamically
FACTOR = 100

def build_rules(sol_data):
    clusters = {k:v for (k,v) in sol_data['atoms']['rectcluster']}
    rev_clusters = {}
    for k,v in clusters.items():
        rev_clusters[v] = rev_clusters.get(v, []) + [k]

    rectvals = {}
    for rect in sol_data['atoms']['minrectval']:
        cluster = rect[0]
        attr = rect[1]
        vals = tuple(rect[2:])
        if cluster not in rectvals.keys():
            rectvals.update({ cluster: { attr: vals }})
        else:
            rectvals[cluster].update( { attr:vals } )   

    clustervals = {}
    for k,v in rev_clusters.items():
        clustervals.update({ k: [rectvals[cl] for cl in v]})
  
    return clustervals

def rules_to_text(rule_dict):
    rulestr = ""
    for k,v in rule_dict.items():
        rulestr += "Rule(s) for Class {0}\n".format(k)
        for idx,rect in enumerate(v):
            rulestr += "  Rule #{0}\n".format(idx)
            for attr,val in rect.items():
                rulestr += "    {a} is between {l} and {h}\n".format(
                    a = attr, l = val[0], h = val[1]
                )
    return rulestr
    

def solve_asprin(asp_program, asp_facts, clingo_args):
    program = ''
    with open("./asp/"+asp_program+".lp", 'r') as f:
        program = f.read()
    for fact in asp_facts:
        program += fact + " \n"
    
    with tempfile.NamedTemporaryFile() as temp_file:
        temp_file.write(program.encode())
        temp_file.flush()
        process = Popen(["asprin", temp_file.name] + clingo_args, stdout=PIPE, stderr=PIPE)
        parser = Popen(["./asparser/asparser"], stdin=process.stdout, stdout=PIPE, stderr=PIPE)
        while True:
            line = parser.stdout.readline().rstrip()
            if not line:
                break
            parsed_line = line.decode('utf-8)')
            sol_data = json.loads(parsed_line)
            print("FOUND SOLUTION #{0} ({1} / {2} / {3})".format(sol_data["solnum"],
                sol_data["atoms"]["overlapcount"][0][0], sol_data["atoms"]["impurecount"][0][0],
                sol_data["atoms"]["outliercount"][0][0]))
            if "optimum" in sol_data.keys():
                rules = build_rules(sol_data)
                break
        return rules

def test_rules(rules, train_df):
    # TODO: Use created rules to test the train_df
    print(rules)
    print(train_df)
    print("ALL GREEN")
            
            
def main():
    os.environ["PYTHONUNBUFFERED"] = "TRUE"

    # Handling command line arguments
    parser = argparse.ArgumentParser(description='Experimental ASP clustering tool')
    parser.add_argument('file', type=str, help="CSV File")
    parser.add_argument('target', nargs='?', type=str, help="Target Classification Field if any")
    parser.add_argument('-f', '--features', type=int, default=2, help="Number of features used")
    parser.add_argument('-s', '--selfeatures', type=str, nargs='*', help="Selected features by name")
    parser.add_argument('-n', '--nrect', type=int, default=2, help="Number of clusters")
    parser.add_argument('-m', '--mode', choices=['weak', 'heuristic'])
    parser.add_argument('-k', '--kfolds', type=int, default=5, help="Number of KFolds for CrossValidation")

    args = parser.parse_args()

    if args.selfeatures:
        selected_parameters = args.selfeatures
    else:
        selected_parameters = []

    feature_count = max(len(selected_parameters), args.features)
    if feature_count < 2:
        raise SystemExit('Error: Must use more than 2 features for clustering')

    df = pd.read_csv(args.file)
    kf = KFold(n_splits = args.kfolds, shuffle = True, random_state = 2)

    for train_idx,test_idx in kf.split(df):
        train = df.iloc[train_idx]
        test =  df.iloc[test_idx]

        asp_facts = ""
        if args.target:
            asp_facts += "target('{0}').\n".format(args.target)
        
        for att in df.keys():
            asp_facts += "attribute('{0}'). ".format(att)
        asp_facts += "\n"
        for i, row in train.iterrows():
            point = []
            for k,v in row.items():
                if k == args.target:
                    asp_facts += "cluster({0}, '{1}'). ".format(i,v.replace('-','_').lower())
                else:
                    asp_facts += "value({0},'{1}',{2:d}). ".format(i,k,int(float(v)*FACTOR))
                    point.append(v)
            asp_facts += "\n"
        
        # selected parameters facts for asp
        asp_selected_parameters = ""
        for parameter in selected_parameters:
            asp_selected_parameters += "selattr('" + parameter + "')."

        # Use -c selectcount=N to specify the number of dimensions of each rectangle
        # Specify the number of rectangles by changing the nrect value
        options = ['-c','nrect=' + str(args.nrect)]
        options += ['-c','selectcount=' + str(feature_count)]
        if args.mode is not None:
            options += ['--approximation='+ str(args.mode) ]

        optimum_rules = solve_asprin('rectangles_asprin', [asp_facts, asp_selected_parameters], options)

        test_rules(optimum_rules, train)
    
    os.environ["PYTHONUNBUFFERED"] = "FALSE"

if __name__ == "__main__":
    main()