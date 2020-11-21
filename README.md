# ProteusQ Modules

This is the working repository for code update.


# Contributing to the code

## Introduction Note

All contributions to our Qudi Extension modules related to the functionality of the ProteusQ are very welcome!

However, if you want to produce code that might not only be used by yourself, then you have to follow some rules and regulations so that others (and mostly the developers) can easier/faster understand the purpose of your program, the keynote of your algorithm and how to use your program properly.

Keep in mind, that not everyone of us is a natural born programmer! However, the only way to improve yourself is to simply start programming and develop a running code by trial and error, and, very important, to **read** and to **comprehend other code**. So bear in mind: Code is much more read then written!
There are million ways to Rome, but only a few of them are elegant and fast! Therefore, for the sake of easy comprehension, readability and clarity, you have to document and structure your code.


Make it as good as you can. Ask other people or discuss with them. If you feel that you have tried your best to write proper code, or to implement an add-on, fix a bug or improve the current state, then create a separate branch from the master, commit your changes to this branch and submit them in a [merge request](https://docs.gitlab.com/ee/user/project/merge_requests/) to the master branch (via the Gitlab interface). There we can review and discuss your contributions. 

Quick and dirty fixes/codes (that means implicitly that you  **can** actually do it better, but have not put the effort into it to make it good) are not well received in the merge request to the master, hence they should be not submitted and will be rejected. 

If you want to experiment with the code, then simply create your own (local) branch with Git. Try to make the changes atomic (improve parts of the functionality) or group your changes in topics and try to merge to the master whenever your code is runnig properly. Please make sure to properly document and structure your code, so that it can be easily reused and understood by others.


## Why do we use a scripting language like Python?

Scripting languages (Python, Perl, ) differ from programming languages (as C, C++, Fortran, G, ... )  essentially in their performance and also have a considerably different field of applications. Their very high abstraction level makes them more readable for a human being and their intention is not to replace well established powerful programming languages but glue together different components of the system for a much flexible usage.

Have a look at the paper by [John Ousterhout - Scripting: higher level programming for the 21st Century](https://ieeexplore.ieee.org/document/660187) which points out the significance of scripting languages and gives you an idea why we want to use it.

## The Hitchhiker’s Guide to Python 

There exists a very nice [Hitchhiker’s Guide to Python](http://python-guide.readthedocs.org/en/latest/). You should definitely visit this website, since it contains some key aspects for a adequate programming style and some basic tutorials to start programming in python. 

## Learning Python

[https://learnxinyminutes.com/docs/python3/](Learn Python)\
[https://www.python.org/about/gettingstarted/](The Python Tutorial)\
[http://www.python-kurs.eu/](Python-Kurs - German)
[http://www.python-course.eu](Python Course - English)\
[http://www.openbookproject.net/pybiblio/gasp/course/](Gasp Python Course)\
[http://codingbat.com/python](CodingBat code practice)\
[https://developers.google.com/edu/python/](Google for Education - Python)


# Manual installation of the ProteusQ environment

- Install bare python3.8.6

Add python and pip to environment variables

- install modules via pip

python -m pip install --upgrade pip
pip install cycler
pip install cython
pip install ipython

download Visual Studio from 
https://visualstudio.microsoft.com/downloads/#

Select "Desktop development with C++"

build tools for visual studio


It looks like you're trying to remove a component that's required by the following:

-  MSVC v142 - VS 2019 C++ x64/x86 Spectre-mitigated libs (v14.28) 

If you continue, we'll remove the component and any items listed above that depend on it.




C# and Visual Basic Roslyn compilers
MSBuild
C++ core features
MSVC v142 - VS 2019 C++ x64/x86 build tools (v14.28)
Windows 10 SDK (10.0.19041.0)
MSVC v142 - VS 2019 C++ x64/x86 Spectre-mitigate


Download wheel for 'pywinpty' directly from 
https://www.lfd.uci.edu/~gohlke/pythonlibs/#pywinpty
for the correct python version


pip install jupyter

pip install wheel

pip install lxml
pip install matplotlib

pip install asteval
pip install fysom
pip install gitpython    
pip install lmfit
pip install pyflowgraph-qo
pip install pyqtgraph-qo 
pip install pyvisa
pip install rpyc
pip install ruamel.yaml
pip install serial
pip install typing

pip install pyqt5

