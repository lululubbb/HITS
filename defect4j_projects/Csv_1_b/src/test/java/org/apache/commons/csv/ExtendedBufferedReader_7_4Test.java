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

class ExtendedBufferedReader_7_4Test {

    private ExtendedBufferedReader extendedBufferedReader;

    @BeforeEach
    void setUp() {
        Reader dummyReader = new Reader() {
            @Override
            public int read(char[] cbuf, int off, int len) {
                return -1;
            }

            @Override
            public void close() {
            }
        };
        extendedBufferedReader = new ExtendedBufferedReader(dummyReader);
    }

    @Test
    @Timeout(8000)
    void testGetLineNumber_initialValue() throws Exception {
        Method getLineNumberMethod = ExtendedBufferedReader.class.getDeclaredMethod("getLineNumber");
        getLineNumberMethod.setAccessible(true);
        int lineNumber = (int) getLineNumberMethod.invoke(extendedBufferedReader);
        assertEquals(0, lineNumber);
    }

    @Test
    @Timeout(8000)
    void testGetLineNumber_afterSettingLineCounter() throws Exception {
        // Use reflection to set private field lineCounter
        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        lineCounterField.setInt(extendedBufferedReader, 5);

        Method getLineNumberMethod = ExtendedBufferedReader.class.getDeclaredMethod("getLineNumber");
        getLineNumberMethod.setAccessible(true);
        int lineNumber = (int) getLineNumberMethod.invoke(extendedBufferedReader);
        assertEquals(5, lineNumber);
    }
}