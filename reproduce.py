#!/usr/bin/env python
"""
This is a tool to replicate live on-chain events. It starts with a transaction id

1 Fetch the transaction data from an API. 
2 Fetch the data at destination
3 Fetch balance and nonce at source
4 Execute transaction
5 If transaction has any externally reaching ops (BALANCE, EXTCODECOPY, CALL etc), 
  * Fetch info about those accounts
6. Go back to 4 until all account info is fetched. Code, balance, nonce etc. 
7. Generate a genesis, and code to invoke the on-chain event.

"""

import json
import tempfile, os
from evmlab import etherchain
from evmlab import compiler as c
from evmlab import genesis as gen
from web3 import Web3, RPCProvider
from evmlab import multiapi
from sys import argv, exit

def generateCall(addr, gas = None, value = 0, incode=""):
    """ Generates a piece of code which calls the supplies address"""

    p = c.Program()
    if (len(incode)):
        p.push(len(incode) / 2)
        p.push(0)
        p.push(0)
        p._addOp(c.CALLDATACOPY)
    p.call(gas, addr, value, insize=len(incode)/2)
    p.op(c.POP)
    return p.bytecode()

def findExternalCalls(list_of_output):
    externals = {
                "CALL"         : lambda o : o['stack'][-2], 
                "CALLCODE"     : lambda o : o['stack'][-2], 
                "DELEGATECALL" : lambda o : o['stack'][-2], 
                "EXTCODECOPY"  : lambda o : o['stack'][-1],
                "EXTCODESIZE"  : lambda o : o['stack'][-1],
                "BALANCE"      : lambda o : o['stack'][-1],
                }
    accounts = set()
    for l in list_of_output:
        o = json.loads(l.strip())
        if 'opName' in o and o['opName'] in externals.keys():
            accounts.add(externals[o['opName']](o))
    
    return list(accounts)

def debugdump(obj):
    import pprint
    pprint.PrettyPrinter().pprint(obj)



def reproduceTx(txhash, evmbin, api):

    from evmlab import gethvm
    vm = gethvm.VM(evmbin)
    genesis = gen.Genesis()
    



    tx = api.getTransaction(txhash)

    s = tx['from']
    r = tx['to']
    tx['input'] = tx['input'][2:]

    #s = tx['sender']
    #r = tx['recipient']
    debugdump(tx)
    blnum = int(tx['blockNumber'])
    bootstrap = generateCall(r, incode=tx['input'])
    toAdd  = [s,r]
    done = False
    while not done:    
        done = True
        # Add accounts that we know of 
        for x in toAdd:
            if not genesis.has(x): 
                acc = api.getAccountInfo( x , blnum)
                debugdump(acc)
                genesis.add(acc)
                done = False
        if not done:
            #genesis.prettyprint()
            g_path = genesis.export_geth()
            print("Executing tx...")
            output =  vm.execute(code = bootstrap, genesis = g_path, json = True, sender=s, input = tx['input'])
            externalAccounts = findExternalCalls(output)
            print("Externals: %s " % externalAccounts )
            toAdd = externalAccounts
            fd, temp_path = tempfile.mkstemp(dir='.', prefix=txhash+'_', suffix=".txt")
            with open(temp_path, 'w') as f :
                f.write("\n".join(output))
            os.close(fd)
            print("Saved trace to %s" % temp_path)
    print("Genesis complete: %s" % g_path)


def test():
    evmbin = "evm"
#    evmbin = "/home/martin/data/workspace/go-ethereum/build/bin/evm"
    tx = "0x66abc672b9e427447a8a8964c7f4671953fab20571ae42ae6a4879687888c495"
    tx = "0x9dbf0326a03a2a3719c27be4fa69aacc9857fd231a8d9dcaede4bb083def75ec"
    web3 = Web3(RPCProvider(host = 'mainnet.infura.io', port= 443, ssl=True))
    chain = etherchain.EtherChainAPI()
    api = multiapi.MultiApi(web3 = web3, etherchain = chain)
    reproduceTx(tx, evmbin, api)

def fetch(args):
    if len(args) < 1:
        print("Usage: ./reproducy.py <tx hash>")
        exit(1)
    evmbin = "evm"
    tx = args[0]
    web3 = Web3(RPCProvider(host = 'mainnet.infura.io', port= 443, ssl=True))
    chain = etherchain.EtherChainAPI()
    api = multiapi.MultiApi(web3 = web3, etherchain = chain)
    reproduceTx(tx, evmbin, api)


if __name__ == '__main__':
    fetch(argv[1:])
