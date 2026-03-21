package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;
import java.io.IOException;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.Reader;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ExtendedBufferedReader_7_2Test {

    private ExtendedBufferedReader extendedBufferedReader;

    @BeforeEach
    void setUp() {
        Reader reader = new Reader() {
            @Override
            public int read(char[] cbuf, int off, int len) {
                return -1; // simulate end of stream
            }
            @Override
            public void close() {
                // no op
            }
        };
        extendedBufferedReader = new ExtendedBufferedReader(reader);
    }

    @Test
    @Timeout(8000)
    void testGetLineNumber_initialValue() throws Exception {
        Method getLineNumber = ExtendedBufferedReader.class.getDeclaredMethod("getLineNumber");
        getLineNumber.setAccessible(true);
        int lineNumber = (int) getLineNumber.invoke(extendedBufferedReader);
        assertEquals(0, lineNumber);
    }

    @Test
    @Timeout(8000)
    void testGetLineNumber_afterSettingLineCounter() throws Exception {
        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        lineCounterField.set(extendedBufferedReader, 5);

        Method getLineNumber = ExtendedBufferedReader.class.getDeclaredMethod("getLineNumber");
        getLineNumber.setAccessible(true);
        int lineNumber = (int) getLineNumber.invoke(extendedBufferedReader);
        assertEquals(5, lineNumber);
    }
}